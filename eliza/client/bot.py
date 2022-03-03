from shimeji import ChatBot
from shimeji.preprocessor import ContextPreprocessor
from shimeji.postprocessor import NewlinePrunerPostprocessor

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
