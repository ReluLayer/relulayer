import os
import sys
from dotenv import load_dotenv
import anthropic
from google import genai

def test_anthropic():
    print("Testing Anthropic (Claude) API...")
    try:
        # Anthropic SDK automatically picks up ANTHROPIC_API_KEY from environment
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[
                {"role": "user", "content": "Say 'Anthropic API is working' in a short sentence."}
            ]
        )
        print(f"✅ Success! Response: {response.content[0].text}\n")
    except Exception as e:
        print(f"❌ Anthropic API Error: {e}\n")

def test_gemini():
    print("Testing Google (Gemini) API...")
    try:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not found")
            
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents="Say 'Gemini API is working' in a short sentence."
        )
        print(f"✅ Success! Response: {response.text.strip()}\n")
    except Exception as e:
        print(f"❌ Google API Error: {e}\n")

if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()
    
    print("--- API Key Testing Script ---\n")
    test_anthropic()
    test_gemini()
