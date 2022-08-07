import re
from difflib import SequenceMatcher
from typing import List
from discord import Emoji, User

# funky globals
supporter_guild = None
supporter_roles = None

def set_guild(guild):
    global supporter_guild
    supporter_guild = guild

def get_guild():
    global supporter_guild
    return supporter_guild

def set_roles(roles):
    global supporter_roles
    supporter_roles = roles

def get_roles():
    global supporter_roles
    return supporter_roles

def anti_spam(messages, threshold=0.8):
    to_remove = []
    for i in range(len(messages)):
        for j in range(i+1, len(messages)):
            if i != j:
                if SequenceMatcher(None, messages[i].content, messages[j].content).ratio() > threshold:
                    to_remove.append(j)
    to_remove = list(set(to_remove))
    messages = [messages[i] for i in range(len(messages)) if i not in to_remove]
    return messages, len(to_remove)

def replace_emojis_pings(text: str, users: List[User], emojis: List[Emoji]) -> str:
    # sort users from largest username to smallest
    users.sort(key=lambda user: len(user.name), reverse=True)

    for user in users:
        text = text.replace(f'@{user.name}', f'<@{user.id}>')

    for emoji in emojis:
        text = text.replace(f':{emoji.name}:', f'<:{emoji.name}:{emoji.id}>')
    
    # remove any remaining text enclosed in colons
#    text = re.sub(r':\S+:', '', text)
    # remove any excess spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text

def replace_emojis_pings_inverse(text: str, users: List[User], emojis: List[Emoji]) -> str:
    for user in users:
        text = text.replace(f'<@{user.id}>', f'@{user.name}')

    for emoji in emojis:
        text = text.replace(f'<:{emoji.name}:{emoji.id}>', f':{emoji.name}:')
    
    return text

def standardize_punctuation(text):
    text = text.replace("’", "'")
    text = text.replace("`", "'")
    text = text.replace("“", '"')
    text = text.replace("”", '"')
    return text

def fix_trailing_quotes(text):
    num_quotes = text.count('"')
    if num_quotes % 2 == 0:
        return text
    else:
        return text + '"'

def cut_trailing_sentence(text):
    text = standardize_punctuation(text)
    last_punc = max(text.rfind("."), text.rfind("!"), text.rfind("?"), text.rfind(".\""), text.rfind("!\""), text.rfind("?\""), text.rfind(".\'"), text.rfind("!\'"), text.rfind("?\'"))
    if last_punc <= 0:
        last_punc = len(text) - 1
    et_token = text.find("<")
    if et_token > 0:
        last_punc = min(last_punc, et_token - 1)
    text = text[: last_punc + 1]
    text = fix_trailing_quotes(text)
    return text
