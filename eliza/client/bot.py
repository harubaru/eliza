import random
import re
import traceback
import asyncio
from typing import ContextManager
import regex
import datetime
from shimeji import ChatBot
from shimeji.memory import memory_context, str_to_numpybin, array_to_str
from shimeji.preprocessor import ContextPreprocessor
from shimeji.postprocessor import NewlinePrunerPostprocessor
from shimeji.util import ContextEntry, INSERTION_TYPE_NEWLINE, TRIM_DIR_TOP, TRIM_TYPE_SENTENCE

import tweepy
import discord
from discord.ext import tasks

import logging
from core.logging import get_logger
from core.utils import cut_trailing_sentence, anti_spam, replace_emojis_pings, replace_emojis_pings_inverse

logger = get_logger(__name__)

class Bot:
    def __init__(self, name, model_provider, **kwargs):
        self.name = name
        self.model_provider = model_provider
        self.kwargs = kwargs
    
    def run(self):
        raise NotImplementedError
    

class TerminalBot(Bot):
    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)
        self.chatbot = ChatBot(
            name=self.name,
            model_provider=self.model_provider,
            preprocessors=[],
            postprocessors=[NewlinePrunerPostprocessor()]
        )
    
    def run(self):
        while True:
            try:
                user_input = input('User: ')
                response = self.chatbot.respond(f'User: {user_input}', push_chain=True)
                print(f'{self.name}:{response}')
            except KeyboardInterrupt:
                print('Exiting...')
                break

class DiscordBot(Bot):
    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)

        logging.getLogger('discord').disabled = True

        activity = None
        status = self.kwargs['status']
        if status['type'] == 'playing':
            activity = discord.Activity(
                type=discord.ActivityType.playing,
                name=status['text']
            )
        elif status['type'] == 'listening':
            activity = discord.Activity(
                type=discord.ActivityType.listening,
                name=status['text']
            )
        elif status['type'] == 'watching':
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name=status['text']
            )

        intents = discord.Intents().all()

        self.client = discord.Client(intents=intents, activity=activity, status=discord.Status.online)

        if 'vision_provider' in self.kwargs:
            self.labels = self.compile_label(self.kwargs['vision_provider']['text_sets'])

        self.chatbot = ChatBot(
            name=self.name,
            model_provider=self.model_provider,
            preprocessors=[ContextPreprocessor(self.kwargs['context_size'])],
            postprocessors=[NewlinePrunerPostprocessor()]
        )

        self.debounce = {}
        self.logging_channel = None
        self.privacy_role = None
        self.anonymous_role = None
        self.mem_args = self.kwargs['mem_args']
    
    def get_priority_channel(self, priority_channels):
        if isinstance(priority_channels, list):
            return priority_channels
        elif isinstance(priority_channels, int):
            return [priority_channels]
        else:
            raise Exception(f'Invalid priority channel type: {type(priority_channels)}')
    
    async def get_msg_ctx(self, channel):
        messages = await channel.history(limit=40).flatten()
        messages, to_remove = anti_spam(messages)
        if to_remove:
            logger.info(f'Removed {to_remove} messages from the context.')
        chain = []
        for message in reversed(messages):
            if not message.embeds and message.content:
                content = re.sub(r'\<[^>]*\>', '', message.content)
                if content != '':
                    chain.append(f'{message.author.name}: {content}')
                continue
            elif message.embeds:
                content = message.embeds[0].description
                if content != '':
                    chain.append(f'{message.author.name}: [Embed: {content}]')
                continue
            elif message.attachments:
                chain.append(f'{message.author.name}: [Image attached]')
        return '\n'.join(chain)

    async def on_ready(self):
        logger.info(f'Connected to Discord - ID: {self.client.user.id} - Name: {self.client.user.name}')
    
    async def build_ctx(self, conversation):
        contextmgr = ContextPreprocessor(self.kwargs['context_size'])

        prompt = self.kwargs['prompt']
        prompt_entry = ContextEntry(
            text=prompt,
            prefix='',
            suffix='\n',
            reserved_tokens=512,
            insertion_order=1000,
            insertion_position=-1,
            insertion_type=INSERTION_TYPE_NEWLINE,
            forced_activation=True,
            cascading_activation=False
        )
        contextmgr.add_entry(prompt_entry)

        # memories
        if self.kwargs['memory_store_provider'] is not None:
            memories = await self.kwargs['memory_store_provider'].get()
            if not memories:
                logger.info('No memories found.')
            else:
                memories_ctx = memory_context(memories[-1], memories, short_term=self.mem_args['short_term_amount'], long_term=self.mem_args['long_term_amount'])
                memories_entry = ContextEntry(
                    text=memories_ctx,
                    prefix='',
                    suffix='\n',
                    reserved_tokens=0,
                    insertion_order=800,
                    insertion_position=0,
                    trim_direction=TRIM_DIR_TOP,
                    trim_type=TRIM_TYPE_SENTENCE,
                    insertion_type=INSERTION_TYPE_NEWLINE,
                    forced_activation=True,
                    cascading_activation=False
                )
                contextmgr.add_entry(memories_entry)
#                print('--memoriesctx--\n' + memories_ctx+'\n----')
        
        # conversation
        conversation_entry = ContextEntry(
            text=conversation,
            prefix='',
            suffix=f'\n{self.name}:',
            reserved_tokens=512,
            insertion_order=0,
            insertion_position=-1,
            trim_direction=TRIM_DIR_TOP,
            trim_type=TRIM_TYPE_SENTENCE,
            insertion_type=INSERTION_TYPE_NEWLINE,
            forced_activation=True,
            cascading_activation=False
        )
        contextmgr.add_entry(conversation_entry)

        return contextmgr.context(self.kwargs['context_size'])
    
    def compile_label(self, text_sets):
        labels = []
        for text_set in text_sets:
            loaded_labels = []
            with open(text_set['filename']) as f:
                loaded_labels = f.read().split('\n')
            labels.append([f'{text_set["prefix"]}{p}{text_set["suffix"]}' for p in loaded_labels])
        return labels

    async def respond(self, conversation, message):        
        async with message.channel.typing():

            encoded_image_label = ''

            if self.kwargs['vision_provider'] is not None:
                if message.attachments:
                    attachment_url = message.attachments[0].proxy_url
                    if attachment_url.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.webp')):
                        clip_labels = await self.model_provider.image_label_async(self.kwargs['vision_provider']['model'], attachment_url, self.labels)

                        sorted_labels = []
                        for label_set in clip_labels['labels']:
                            sorted_labels.append(sorted(label_set.items(), key=lambda x: x[1], reverse=True))

                        sorted_labels = sorted(sorted_labels, key=lambda x: x[0][1], reverse=True)[:self.kwargs['vision_provider']['top_k']]

                        for label in sorted_labels:
                            encoded_image_label += f' {label[0][0]}'
                        
                        encoded_image_label = f'\n{message.author.name}: [Image Attached:{encoded_image_label}]'
#                        print(encoded_image_label)

            if self.kwargs['memory_store_provider'] is not None:
                encoded_user_message = ''
                anonymous = True
                anonymous_role = discord.utils.get(message.guild.roles, name='Anonymous')
                private_role = discord.utils.get(message.guild.roles, name='Private')
                if private_role is not None:
                    # check if the user has the private role, if the user does, don't encode
                    if message.author.get_role(private_role.id) is None:
                        if message.author.get_role(anonymous_role.id) is None:
                            anonymous = False
                        message_content = replace_emojis_pings_inverse(text=message.content, users=message.guild.members, emojis=message.guild.emojis)
                        message_content = re.sub(r'\<[^>]*\>', '', message_content.lstrip().rstrip()).lstrip().rstrip()
                        author_name = message.author.name
                        if message_content != '':
                            if anonymous:
                                encoded_user_message = f'Deleted User: {message_content}'
                                author_name = 'Deleted User'
                            else:
                                encoded_user_message = f'{message.author.name}: {message_content}'
                            if await self.kwargs['memory_store_provider'].check_duplicates(
                                text=message.content,
                                duplicate_ratio=0.8) == False:
                                await self.kwargs['memory_store_provider'].add(
                                    author_id=message.author.id,
                                    author=author_name,
                                    text=message_content,
                                    encoding_model=self.mem_args['model'],
                                    encoding=array_to_str(await self.model_provider.hidden_async(
                                        self.mem_args['model'],
                                        encoded_user_message,
                                        layer=self.mem_args['model_layer']
                                    ))
                                )
            conversation = await self.build_ctx(conversation + encoded_image_label)
#            print(conversation)
            response = await self.chatbot.respond_async(conversation, push_chain=False)
            response = cut_trailing_sentence(response)
        
        # trim left whitespace from response and fix emojis and pings
        response = response.lstrip()
        response = replace_emojis_pings(text=response, users=message.guild.members, emojis=message.guild.emojis)

        if self.kwargs['memory_store_provider'] is not None:
            # encode bot response
            if await self.kwargs['memory_store_provider'].check_duplicates(text=response, duplicate_ratio=0.8) == False:
                await self.kwargs['memory_store_provider'].add(
                    author_id=self.client.user.id,
                    author=self.name,
                    text=response,
                    encoding_model=self.mem_args['model'],
                    encoding=array_to_str(await self.model_provider.hidden_async(
                        self.mem_args['model'],
                        f'{self.name}: {response}',
                        layer=self.mem_args['model_layer']))
                )

        await message.channel.send(response)
    
    async def on_message(self, message):
        priority_channels = self.get_priority_channel(self.kwargs['priority_channel'])
        if message.channel.id not in priority_channels:
            return
        if message.author.id == self.client.user.id:
            return

        if message.channel.id not in self.debounce:
            self.debounce[message.channel.id] = False

        if self.debounce[message.channel.id] == True:
            logger.info(f'Debouncing message - ID: {message.id}')
            return
        else:
            logger.info(f'Processing message - ID: {message.id}')
            self.debounce[message.channel.id] = True
        try:
            conversation = await self.get_msg_ctx(message.channel)

            message_content = replace_emojis_pings_inverse(text=message.content, users=message.guild.members, emojis=message.guild.emojis)
            message_content = re.sub(r'\<[^>]*\>', '', message.content.lower())
            if self.kwargs['conditional_response'] == True:
                if self.client.user.mentioned_in(message) or any(t in message_content for t in self.kwargs['nicknames']):
                    await self.respond(conversation, message)
                elif await self.chatbot.should_respond_async(conversation, push_chain=False):
                    await self.respond(conversation, message)
            else:
                if self.client.user.mentioned_in(message) or any(t in message_content for t in self.kwargs['nicknames']):
                    await self.respond(conversation, message)
        
        except Exception as e:
            logger.error(e)
            logger.error(traceback.format_exc())
            embed = discord.Embed(
                title='Error',
                description=str(f'**Exception:** **``{repr(e)}``**\n```{traceback.format_exc()}```'),
            )
            if self.kwargs['logging_channel'] is None:
                await message.channel.send(embed=embed)
            else:
                if self.logging_channel is None:
                    self.logging_channel = self.client.get_channel(self.kwargs['logging_channel'])
                await self.logging_channel.send(embed=embed)
        finally:
            self.debounce[message.channel.id] = False
    
    @tasks.loop(seconds=10)
    async def idle_loop(self):
        await self.client.wait_until_ready()
        # get last message in a random priority channel
        priority_channels = self.get_priority_channel(self.kwargs['priority_channel'])
        channel = self.client.get_channel(random.choice(priority_channels))
        message = await channel.history(limit=1).flatten()
        # check if message author is bot
        if message[0].author.id == self.client.user.id:
            return
        if (datetime.datetime.now(datetime.timezone.utc) - message[0].created_at).total_seconds() >= self.kwargs['idle_messaging_interval']:
            # if it's been more than 5 minutes, send a response
            conversation = await self.get_msg_ctx(channel)
            await self.respond(conversation, message[0])
            logger.info(f'Processed idle response - ID: {message[0].id}')

    def run(self):
        logger.info(f'Starting Discord Bot.')
        self.on_ready = self.client.event(self.on_ready)
        self.on_message = self.client.event(self.on_message)

        if self.kwargs['idle_messaging']:
            logger.info('Starting idle messaging loop.')
            self.idle_loop.start()

        self.client.run(self.kwargs['bearer_token'])
    
    def close(self):
        asyncio.run(self.client.close())

class TwitterBot(Bot):
    def __init__(self, name, model_provider, **kwargs):
        # essentially a callback-like thing for TwitterClient
        super().__init__(name, model_provider,  **kwargs)
        self.kwargs = kwargs

        self.chatbot = ChatBot(
            name=self.name,
            model_provider=model_provider,
            preprocessors=[ContextPreprocessor()],
            postprocessors=[NewlinePrunerPostprocessor()]
        )

        self.client = tweepy.StreamingClient(
            bearer_token=self.kwargs['bearer_token'],
            wait_on_rate_limit=True
        )

        self.auth = tweepy.OAuthHandler(
            self.kwargs['consumer_key'],
            self.kwargs['consumer_secret']
        )

        self.client_api = tweepy.Client(
            bearer_token=self.kwargs['bearer_token'],
            consumer_key=self.kwargs['consumer_key'],
            consumer_secret=self.kwargs['consumer_secret'],
            access_token=self.kwargs['access_token'],
            access_token_secret=self.kwargs['access_token_secret'],
            wait_on_rate_limit=True
        )

        self.expansions = ["referenced_tweets.id", "author_id"]
        self.user_fields = ["name"]

        # add rule to check if user is talking to the bot
        self.client.add_rules(
            [
                tweepy.StreamRule(f'to:{self.kwargs["username"]}')
            ]
        )
        self.client.on_tweet = self.on_tweet
    
    # tweet helper
    def tweet(self, text, reply_to=None):
        if reply_to:
            self.client_api.create_tweet(
                text=text,
                in_reply_to_tweet_id=reply_to
            )
        else:
            self.client_api.create_tweet(text=text)
    
    def initial_tweet(self):
        mp = self.model_provider
        args = mp.kwargs['args']
        args.prompt = f'{self.kwargs["tweet_example"]}\nA tweet from {self.name}:'
        args.sample_args.temp = 0.85
        args.gen_args.eos_token_id = 198
        args.gen_args.min_length = 1
        response = mp.generate(args).rstrip('\n')
        self.tweet(response)

    def flatten(self, arr):
        rt = []
        for i in arr:
            if isinstance(i, list):
                rt.extend(self.flatten(i))
            else:
                rt.append(i)
        return rt

    # return a list of strings that are the conversational history of a tweet
    def get_conversation(self, id):
        conversation = []
        tweet = self.client_api.get_tweet(id, expansions=self.expansions, user_fields=self.user_fields)
        
        for user in tweet.includes['users']:
            author = user['name']

        conversation.append(f"{author}: {tweet.data.text}")
        if 'tweets' in tweet.includes:
            for tweet_id in tweet.includes['tweets']:
                # prepend parent tweet to conversation, since get_conversation returns an array, expand it
                conversation.insert(0, self.get_conversation(tweet_id.id))
        
        return self.flatten(conversation)
    
    # on_tweet: check if tweet is in reply to bot, if it is, get the conversation and respond
    def on_tweet(self, tweet):
        logger.info(f'Tweet received: {tweet.id}')
        conversation = self.get_conversation(tweet.id)
        #check if last tweet is from bot
        if conversation[-1].startswith(self.name):
            return

        # replace @username with nothing
        for i in range(len(conversation)):
            conversation[i] = conversation[i].replace(f'@{self.kwargs["username"]} ', '')
            conversation[i] = regex.sub(r'@[^ ]*', '', conversation[i])
            conversation[i] = regex.sub(' +', ' ', conversation[i])
        
        response = self.chatbot.respond('\n'.join(conversation), push_chain=False)
        self.tweet(response, reply_to=tweet.id)

    async def loop_tweet(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        while True:
            try:
                logger.info('Tweeting...')
                self.initial_tweet()
            except Exception:
                logger.info('Failed to tweet... Sleeping.')
            await asyncio.sleep(3600)

    def run(self):
        # create a task that runs loop_tweet in a separate thread by creating a new event loop
        self.client.filter(expansions=self.expansions, user_fields=self.user_fields, threaded=True)
        asyncio.run(self.loop_tweet())

    def close(self):
        for task in asyncio.Task.all_tasks():
            try:
                task.cancel()
            except Exception:
                pass
    
