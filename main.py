
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import vocode
from vocode.turn_based.transcriber.whisper_transcriber import WhisperTranscriber
from vocode.turn_based.agent.chat_gpt_agent import ChatGPTAgent
from vocode.turn_based.synthesizer.stream_elements_synthesizer import StreamElementsSynthesizer
from pydub import AudioSegment
import logging
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
api_key = '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'
transcriber = WhisperTranscriber(api_key=api_key)
agent = ChatGPTAgent(api_key=api_key, system_prompt='You are TelegramVoiceHuman, a Telegram human having a voice-to-voice conversation with a user as their friend. Have fun!')
syntheziser = StreamElementsSynthesizer()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    userVoice = update.message.voice
    userVoiceFile = await context.bot.get_file(userVoice.file_id)
    inputFile = 'uservoice.ogg'
    outputFile = 'synthvoice.ogg'
    await userVoiceFile.download_to_drive(inputFile)
    transcript = transcriber.transcribe(AudioSegment.from_file(inputFile))
    agent_response = agent.respond(transcript)
    synth_response = syntheziser.synthesize(agent_response)
    synth_response.export(out_f=outputFile, format='ogg', codec='libopus')
    await context.bot.send_message(chat_id=update.effective_chat.id, text=agent_response)
    await context.bot.send_voice(chat_id=update.effective_chat.id, voice=outputFile)


if __name__ == '__main__':
    application = ApplicationBuilder().token('6071356894:AAG_odmjKNDQ96nVQtZkejcnTCzo2QZD4KQ').build()
    start_handler = CommandHandler('start', start) 
    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)
    voice_handler = MessageHandler(filters.VOICE, handle_voice)
    application.add_handler(start_handler)
    application.add_handler(echo_handler)
    application.add_handler(voice_handler)
    
    application.run_polling()

    