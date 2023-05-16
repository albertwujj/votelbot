from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

import vocode
from vocode.turn_based.transcriber.whisper_transcriber import WhisperTranscriber
from vocode.turn_based.agent.chat_gpt_agent import ChatGPTAgent
from vocode.turn_based.synthesizer.stream_elements_synthesizer import StreamElementsSynthesizer
from vocode.turn_based.synthesizer.eleven_labs_synthesizer import ElevenLabsSynthesizer
from vocode.turn_based.synthesizer.play_ht_synthesizer import PlayHtSynthesizer
from pydub import AudioSegment
import logging
import os
from typing import Tuple

# Your chosen synthesizer provider's corresponding Vocode turn_based class instance
######SYNTH = ElevenLabsSynthesizer(api_key=os.environ['ELEVEN_LABS_API_KEY'])
# An dict of voices you want the user to be able to choose from, for each entry the key=provider_voice_id and value=name_displayed_to_user
VOICE_NAME_TO_ID = {'obama': 'zzHoZ9isaKwC4fEv7Idf', 'biden': 'mqRQRcVDz2T5TcqF5vGi'}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# key=synth class, value=attribute that chooses the provider voice
voice_attr_of = {ElevenLabsSynthesizer: 'voice_id', PlayHtSynthesizer: 'voice'}

class VocodeBotResponder():
    def __init__(self, transcriber, agent, synthesizer):
        self.transcriber = transcriber
        self.agent = agent
        self.synthesizer = synthesizer

    def get_response(self, voice_input: AudioSegment) -> Tuple[str, AudioSegment]:
        transcript = self.transcriber.transcribe(voice_input)
        agent_response = self.agent.respond(transcript)
        synth_response = self.synthesizer.synthesize(agent_response)
        return agent_response, synth_response

    async def handle_telegram_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a voice bot, please send voice messages to me!")

    async def handle_telegram_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        input_file = 'uservoice.ogg'
        output_file = 'synthvoice.ogg'
        user_telegram_voice = await context.bot.get_file(update.message.voice.file_id)
        await user_telegram_voice.download_to_drive(input_file)
        user_voice = AudioSegment.from_file(input_file)
        agent_response, synth_response = self.get_response(user_voice)
        synth_response.export(out_f=output_file, format='ogg', codec='libopus')

        await context.bot.send_message(chat_id=update.effective_chat.id, text=agent_response)
        await context.bot.send_voice(chat_id=update.effective_chat.id, voice=output_file)

    async def handle_telegram_select_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        voice_name = context.args[0]
        setattr(self.synthesizer, voice_attr_of[type(self.synthesizer)], VOICE_NAME_TO_ID[voice_name])

    async def handle_telegram_list_voices(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        voices = "\n".join(VOICE_NAME_TO_ID.keys())
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Available voices:\n{voices}")

    async def handle_telegram_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = '''
I'm a voice bot, here to talk with you! Here's what you can do:

- Send me a voice message and I'll respond with a voice message.
- Use /voice <voice_name> to change the voice I use to respond.
- Use /list to see a list of available voices.
- Use /help to see this help message again.
'''
        await context.bot.send_message(chat_id=update.effective_chat.id, text=help_text)

if __name__ == '__main__':
    transcriber = WhisperTranscriber()
    agent = ChatGPTAgent(system_prompt='You are TelegramHuman, a Telegram human having a voice-to-voice conversation with a user as their friend. Have fun!')
    synthesizer = ElevenLabsSynthesizer('mqRQRcVDz2T5TcqF5vGi')
    voco = VocodeBotResponder(transcriber, agent, synthesizer)
    application = ApplicationBuilder().token(os.environ['TELEGRAM_BOT_KEY']).build()
    start_handler = CommandHandler('start', voco.handle_telegram_start)
    voice_handler = MessageHandler(filters.VOICE & (~filters.COMMAND), voco.handle_telegram_voice)
    select_handler = CommandHandler('voice', voco.handle_telegram_select_voice)
    list_handler = CommandHandler('list', voco.handle_telegram_list_voices)
    help_handler = CommandHandler('help', voco.handle_telegram_help)
    application.add_handler(start_handler)
    application.add_handler(voice_handler)
    application.add_handler(select_handler)
    application.add_handler(list_handler)
    application.add_handler(help_handler)
    application.run_polling()

    