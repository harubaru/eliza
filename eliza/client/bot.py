import random
import re
import traceback
import asyncio
import regex
import datetime
from shimeji import ChatBot
from shimeji.preprocessor import ContextPreprocessor
from shimeji.postprocessor import NewlinePrunerPostprocessor

import tweepy
import discord
from discord.ext import tasks

import logging
from core.logging import get_logger

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
            preprocessors=[ContextPreprocessor()],
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

        self.chatbot = ChatBot(
            name=self.name,
            model_provider=self.model_provider,
            preprocessors=[ContextPreprocessor(self.kwargs['context_size'])],
            postprocessors=[NewlinePrunerPostprocessor()]
        )

        self.debounce = False
    
    def get_priority_channel(self, priority_channels):
        if isinstance(priority_channels, list):
            return priority_channels
        elif isinstance(priority_channels, int):
            return [priority_channels]
        else:
            raise Exception(f'Invalid priority channel type: {type(priority_channels)}')
    
    async def get_msg_ctx(self, channel):
        messages = await channel.history(limit=40).flatten()
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
    
    async def respond(self, conversation, message):
        async with message.channel.typing():
            response = await self.chatbot.respond_async(conversation, push_chain=False)
        await message.channel.send(response)
    
    async def on_message(self, message):
        priority_channels = self.get_priority_channel(self.kwargs['priority_channel'])
        if message.channel.id not in priority_channels:
            return
        if message.author.id == self.client.user.id:
            return

        if self.debounce:
            logger.info(f'Debouncing message - ID: {message.id}')
            return
        else:
            logger.info(f'Processing message - ID: {message.id}')
            self.debounce = True
        try:
            conversation = await self.get_msg_ctx(message.channel)

            if self.kwargs['conditional_response'] == True:
                if self.client.user.mentioned_in(message) or any(t in message.content.lower() for t in self.kwargs['nicknames']):
                    await self.respond(conversation, message)
                elif await self.chatbot.should_respond_async(conversation, push_chain=False):
                    await self.respond(conversation, message)
            else:
                await self.respond(conversation, message)
        except Exception as e:
            logger.error(e)
            logger.error(traceback.format_exc())
            embed = discord.Embed(
                title='Error',
                description=str(f'Exception Type: ``{repr(e)}``\Traceback: ``{traceback.format_exc()}``'),
            )
            await message.channel.send(embed=embed)
        finally:
            self.debounce = False
    
    @tasks.loop(seconds=30)
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
    
