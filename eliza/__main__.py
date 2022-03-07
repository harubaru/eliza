from core.args import parse, config, get_model_provider
from core.logging import get_logger
from client.bot import TerminalBot, TwitterBot

import sys
import asyncio
import traceback

logger = get_logger(__name__)

def main():
    chatbot_config = config(parse())
    try:
        model_provider = get_model_provider(chatbot_config)
        if chatbot_config['client'] == 'terminal':
            bot = TerminalBot(name=chatbot_config['name'], model_provider=model_provider)
            bot.run()
        elif chatbot_config['client'] == 'twitter':
            bot = TwitterBot(
                name=chatbot_config['name'],
                model_provider=model_provider,
                bearer_token=chatbot_config['client_args']['bearer_token'],
                consumer_key=chatbot_config['client_args']['consumer_key'],
                consumer_secret=chatbot_config['client_args']['consumer_secret'],
                access_token=chatbot_config['client_args']['access_token'],
                access_token_secret=chatbot_config['client_args']['access_token_secret'],
                username=chatbot_config['client_args']['username'],
                tweet_example=chatbot_config['client_args']['tweet_example']
            )
            bot.run()
        else:
            raise Exception('unsupported client')
    except KeyboardInterrupt:
        print('Exiting...')
        bot.close()
        sys.exit(0)
    except Exception as e:
        logger.error(e)
        logger.error(traceback.format_exc())
        bot.close()
        sys.exit(1)
    finally:
        bot.close()
        sys.exit(0)

if __name__ == '__main__':
    main()
