from core.args import parse, config, get_model_provider
from core.logging import get_logger
from client.bot import TerminalBot

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
        else:
            raise Exception('unsupported client')
    except KeyboardInterrupt:
        print('Exiting...')
        sys.exit(0)
    except Exception as e:
        logger.error(e)
        logger.error(traceback.format_exc())
        sys.exit(1)
    finally:
        sys.exit(0)

if __name__ == '__main__':
    main()
