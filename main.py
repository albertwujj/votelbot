from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

import vocode
from vocode.turn_based.transcriber.whisper_transcriber import WhisperTranscriber
from vocode.turn_based.agent.chat_gpt_agent import ChatGPTAgent
from vocode.turn_based.synthesizer.stream_elements_synthesizer import StreamElementsSynthesizer
from pydub import AudioSegment
import logging
import os
from typing import Tuple

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

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


if __name__ == '__main__':
    transcriber = WhisperTranscriber()
    agent = ChatGPTAgent(system_prompt='You are TelegramHuman, a Telegram human having a voice-to-voice conversation with a user as their friend. Have fun!')
    synthesizer = StreamElementsSynthesizer()
    voco = VocodeBotResponder(transcriber, agent, synthesizer)
    application = ApplicationBuilder().token(os.environ['TELEGRAM_BOT_KEY']).build()
    start_handler = CommandHandler('start', voco.handle_telegram_start) 
    voice_handler = MessageHandler(filters.VOICE & (~filters.COMMAND), voco.handle_telegram_voice)
    application.add_handler(start_handler)
    application.add_handler(voice_handler)

    application.run_polling()

    