from multiprocessing.connection import wait
from shimeji import ChatBot
from shimeji.preprocessor import ContextPreprocessor
from shimeji.postprocessor import NewlinePrunerPostprocessor

import tweepy

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
            bearer_token=self.kwargs['bearer_token']
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
    
    # return a list of strings that are the conversational history of a tweet
    def get_conversation(self, id):
        conversation = []
        expansions = ["referenced_tweets.id", "author_id"]
        user_fields = ["name"]
        tweet = self.client_api.get_tweet(id, expansions=expansions, user_fields=user_fields)
        # tweet is a request object, which has the dict of the tweet
        for user in tweet.data['includes']['users']:
            if user['id'] == tweet.data['data']['author_id']:
                author = user['name']
        
        conversation.append(f"{author}: {tweet.data['data']['text']}")
        if 'referenced_tweets' in tweet.data['data']:
            for tweet_id in tweet.data['data']['referenced_tweets']:
                conversation.append(self.get_conversation(tweet_id['id']))
        
        return conversation
    
    # on_tweet: check if tweet is in reply to bot, if it is, get the conversation and respond
    def on_tweet(self, tweet):
        if tweet.in_reply_to_user_id:
            conversation = self.get_conversation(tweet.id)
            response = self.chatbot.respond(conversation, push_chain=False)
            self.tweet(response, reply_to=tweet.id)

    def run(self):
        self.client.filter()
