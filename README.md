# eliza

Hello! Welcome to the GitHub page for Eliza!

Eliza is a customizable framework for creating open-domain chatbots on the fly.


## Table of Contents

1. [Introduction](#introduction)
2. [Setup](#setup)
3. [Configuration](#configuration)
4. [Run](#run)

## Introduction

Eliza is a framework that provides all of the essentials necessary to build an open-domain chatbot capable of fulfilling basic needs in natural language. This repo holds our implementation for these essentials, including modules that perform core NLP, context building, and more.

## Setup

Firstly, a [Sukima Backend](https://github.com/hitomi-team/sukima) is required to be running to host Eliza locally. In order to install and setup Sukima, please [click here.](https://github.com/hitomi-team/sukima/wiki/Setup)

Then, you will have to clone and setup Eliza by running these commands:

``$ git clone https://github.com/harubaru/eliza``

``$ cd eliza``

``$ pip install -r requirements.txt``

## Configuration

After the setup is complete, you can use one of our default configurations listed in the ``config`` folder, or you can create your own by using the default as a template.

## Run

Then finally, to run the chatbot, all you would need to do is to run this command with your selected config file.

``$ python eliza --config=config/twitter_yukari_yakumo.json``

![image](https://user-images.githubusercontent.com/26317155/157097205-032cd4c3-008b-4d32-97f5-2b480d7530ca.png)

### License
[GNU Public License version 2.0](LICENSE)

### Any questions? Come hop on by to our Discord server!

![Discord Server](https://discordapp.com/api/guilds/930499730843250783/widget.png?style=banner2)
