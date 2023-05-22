from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

import vocode
from vocode.turn_based.transcriber.whisper_transcriber import WhisperTranscriber
from vocode.turn_based.agent.chat_gpt_agent import ChatGPTAgent
from vocode.turn_based.synthesizer.stream_elements_synthesizer import StreamElementsSynthesizer
from vocode.turn_based.synthesizer.eleven_labs_synthesizer import ElevenLabsSynthesizer
from vocode.turn_based.synthesizer.play_ht_synthesizer import PlayHtSynthesizer
from vocode.turn_based.synthesizer.azure_synthesizer import AzureSynthesizer
from vocode.turn_based.synthesizer.coqui_synthesizer import CoquiSynthesizer
from vocode.turn_based.synthesizer.coqui_tts_synthesizer import CoquiTTSSynthesizer
from vocode.turn_based.synthesizer.rime_synthesizer import RimeSynthesizer

from pydub import AudioSegment
import io
import logging
import os
import subprocess
import inspect
from typing import Tuple

logging.basicConfig(
 format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
 level=logging.INFO)

# Synthesizer class must be one of the following (do not change without adding support):
supported_classes = [StreamElementsSynthesizer, ElevenLabsSynthesizer, PlayHtSynthesizer, AzureSynthesizer, CoquiSynthesizer, CoquiTTSSynthesizer, RimeSynthesizer]

''' CONFIGURATION START '''
# Required environment variables containing API key: OPENAI_API_KEY, TELEGRAM_BOT_KEY, and your Vocode synthesizers classes corresponding API key variable

# Your chosen synthesizer provider's corresponding Vocode turn_based class instance
SYNTH = ElevenLabsSynthesizer('mqRQRcVDz2T5TcqF5vGi',
                              api_key=os.environ['ELEVEN_LABS_API_KEY'])
# An dict of voices you want the user to be able to choose from, for each entry the key=name_displayed_to_user and value=provider_voice_id
# the voice display name must not contain spaces and two names must not be equivalent on a case-insensitive basis (the user is still shown the capitalization but can select names case-insensitively). The language model will also be given the display name as part of its identity. 
VOICE_NAME_TO_ID = {
 'BarackObama': 'zzHoZ9isaKwC4fEv7Idf',
 'JoeBiden': 'mqRQRcVDz2T5TcqF5vGi'
}
# instructions to the language model responsible for generating response transcript.
SYSTEM_PROMPT = 'You are having a voice-to-voice conversation with a user. Always pretend you are a real human. Do not avoid or decline to answer questions because you are not human.'
''' CONFIGURATION END '''
# will be passed the voice display name.
SYSTEM_PROMPT += 'You are {0}. Act like {0} and identify yourself as {0}.'

def assert_correct_names(names):
	lower_name_set = set()
	for name in names:
		assert ' ' not in name, 'Voice display names cannot have spaces!'
		lower_name = name.lower()
		assert (
		 lower_name not in lower_name_set
		), 'Voice display names cannot have duplicates, this requirement is case-insensitive!'
		lower_name_set.add(lower_name)
assert_correct_names(VOICE_NAME_TO_ID.keys())

# key=synth class, value=attribute that chooses the provider voice
voice_attr_of = {
 ElevenLabsSynthesizer: 'voice_id',
 PlayHtSynthesizer: 'voice',
 StreamElementsSynthesizer: 'voice',
 AzureSynthesizer: 'voice_name',
 CoquiSynthesizer: 'voice_id',
 CoquiTTSSynthesizer: 'speaker',
 RimeSynthesizer: 'speaker'
}
assert set(voice_attr_of.keys()) == set(supported_classes), 'supported_classes must match the keys of voice_attr_of!'

assert type(SYNTH) in voice_attr_of.keys(), 'Synthesizer class must be one of the supported ones!'
# check voice_attr_of is correct by asserting all classes have their corresponding value as a parameter in the init function
for key, value in voice_attr_of.items():
	assert value in inspect.signature(key.__init__).parameters


class VocodeBotResponder():

	def __init__(self, transcriber, system_prompt, synthesizer, voice_name_to_id=None):
		self.transcriber = transcriber
		self.system_prompt = system_prompt
		self.synthesizer = synthesizer
		self.chat_ids = []
		if voice_name_to_id:
			self.voice_name_to_id = voice_name_to_id
		else:
			voice = getattr(self.synthesizer, voice_attr_of[self.synthesizer])
			self.voice_name_to_id = {voice: voice}
		self.voice_id_to_name = {v_id: v_name for v_name, v_id in self.voice_name_to_id.items()}
		self.agents = {}

	def get_agent(self, chat_id):
		if chat_id not in self.agents:
			self.agents[chat_id] = {}
			for voice_name in self.voice_name_to_id.keys():
				self.agents[chat_id][voice_name] = ChatGPTAgent(system_prompt=self.system_prompt.format(voice_name))
		return self.agents[chat_id][self.get_current_voice()]

	def get_response(self, chat_id, voice_input: AudioSegment) -> Tuple[str, AudioSegment]:
		transcript = self.transcriber.transcribe(voice_input)
		agent_response = self.get_agent(chat_id).respond(transcript)
		synth_response = self.synthesizer.synthesize(agent_response)
		return agent_response, synth_response

	def get_current_voice(self):
		current_voice_id = getattr(self.synthesizer,
		                           voice_attr_of[type(self.synthesizer)])
		return self.voice_id_to_name[current_voice_id]

	async def handle_telegram_start(self, update: Update,
	                                context: ContextTypes.DEFAULT_TYPE):
		start_text = '''
I'm a voice chatbot, send a voice message to me and I'll send one back!" Use /help to see available commands.
'''
		await context.bot.send_message(chat_id=update.effective_chat.id,
		                               text=start_text)

	async def handle_telegram_voice(self, update: Update,
	                                context: ContextTypes.DEFAULT_TYPE):
		chat_id = update.effective_chat.id
		user_telegram_voice = await context.bot.get_file(update.message.voice.file_id)
		bytes = await user_telegram_voice.download_as_bytearray()
		user_voice = AudioSegment.from_file(io.BytesIO(bytes), format='ogg', codec='libopus')
		agent_response, synth_response = self.get_response(chat_id, user_voice)
		out_voice = io.BytesIO()
		synth_response.export(out_f=out_voice, format='ogg', codec='libopus')
		await context.bot.send_message(chat_id=update.effective_chat.id,
		                               text=agent_response)
		await context.bot.send_voice(chat_id=chat_id, voice=out_voice)

	async def handle_telegram_select_voice(self, update: Update,
	                                       context: ContextTypes.DEFAULT_TYPE):
		if not (context.args):
			await context.bot.send_message(
			 chat_id=update.effective_chat.id,
			 text='You must include a voice name. Use /list to list available voices')
			return
		selected_voice = context.args[0]
		for voice_name, voice_id in self.voice_name_to_id.items():
			if voice_name.lower() == selected_voice.lower():
				setattr(self.synthesizer, voice_attr_of[type(self.synthesizer)], voice_id)
				await context.bot.send_message(chat_id=update.effective_chat.id,
				                               text='Voice changed successfully!')
				return
		await context.bot.send_message(
		 chat_id=update.effective_chat.id,
		 text=
		 'Sorry, I do not recognize that voice. Use /list to list available voices.')

	async def handle_telegram_list_voices(self, update: Update,
	                                      context: ContextTypes.DEFAULT_TYPE):
		voices = "\n".join(self.voice_name_to_id.keys())
		await context.bot.send_message(chat_id=update.effective_chat.id,
		                               text=f'Available voices:\n{voices}')

	async def handle_telegram_who(self, update: Update,
	                              context: ContextTypes.DEFAULT_TYPE):
		current_voice_name = self.get_current_voice()
		await context.bot.send_message(
		 chat_id=update.effective_chat.id,
		 text=f"I am currently '{current_voice_name}'.")

	async def handle_telegram_help(self, update: Update,
	                               context: ContextTypes.DEFAULT_TYPE):
		help_text = '''
I'm a voice bot, here to talk with you! Here's what you can do:

- Send me a voice message and I'll respond with a voice message.
- Use /voice <voice_name> to change the voice I use to respond.
- Use /list to see a list of available voices.
- Use /who to see what voice I currently am.
- Use /help to see this help message again.
'''
		await context.bot.send_message(chat_id=update.effective_chat.id,
		                               text=help_text)

	async def handle_telegram_unknown_cmd(self, update: Update,
	                                      context: ContextTypes.DEFAULT_TYPE):
		await context.bot.send_message(chat_id=update.effective_chat.id,
		                               text='''
Sorry, I didn\'t understand that command. Use /help to see available commands'''
		                               )

	async def handle_telegram_unknown(self, update: Update,
	                                  context: ContextTypes.DEFAULT_TYPE):
		await context.bot.send_message(chat_id=update.effective_chat.id,
		                               text='''
Sorry, I only respond to voice messages or commands. Use /help for more information.'''
		                               )


if __name__ == '__main__':
	transcriber = WhisperTranscriber()
	synthesizer = SYNTH
	if type(synthesizer) == ElevenLabsSynthesizer:
		subprocess.run(['pip', 'install', 'elevenlabs'])
	voco = VocodeBotResponder(transcriber, SYSTEM_PROMPT, synthesizer, VOICE_NAME_TO_ID)
	application = ApplicationBuilder().token(
	 os.environ['TELEGRAM_BOT_KEY']).build()
	start_handler = CommandHandler('start', voco.handle_telegram_start)
	voice_handler = MessageHandler(filters.VOICE & (~filters.COMMAND),
	                               voco.handle_telegram_voice)
	select_handler = CommandHandler('voice', voco.handle_telegram_select_voice)
	list_handler = CommandHandler('list', voco.handle_telegram_list_voices)
	who_handler = CommandHandler('who', voco.handle_telegram_who)
	help_handler = CommandHandler('help', voco.handle_telegram_help)
	unknown_cmd_handler = MessageHandler(filters.COMMAND,
	                                     voco.handle_telegram_unknown_cmd)
	unknown_handler = MessageHandler(~filters.COMMAND,
	                                 voco.handle_telegram_unknown)

	application.add_handler(start_handler)
	application.add_handler(voice_handler)
	application.add_handler(select_handler)
	application.add_handler(list_handler)
	application.add_handler(who_handler)
	application.add_handler(help_handler)
	application.add_handler(unknown_cmd_handler)
	application.add_handler(unknown_handler)
	application.run_polling()
