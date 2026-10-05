import os
from dotenv import load_dotenv
import anthropic
import google.generativeai as genai

# 1. Load the variables from the .env file into the system environment
load_dotenv()

# 2. The Anthropic SDK automatically looks for 'ANTHROPIC_API_KEY' in the environment
# You don't even need to pass it explicitly if you used the standard naming convention.
anthropic_client = anthropic.Anthropic()

# 3. For Google Gemini, you configure it explicitly using the loaded key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Example Claude Call
def test_claude():
    message = anthropic_client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello, Claude."}]
    )
    print(message.content)