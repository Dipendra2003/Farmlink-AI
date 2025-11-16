import os
import google.generativeai as genai

def test_gemini_api():
    """Test Gemini API with gemini-2.5-flash-lite model"""
    
    # API Key - should be in environment variable for security
    API_KEY = "AIzaSyCWQPALgzSe2YC0FdlzyT8KU700Xf3_7_c"
    MODEL_NAME = "gemini-2.5-flash-lite"
    
    try:
        # Configure the API
        genai.configure(api_key=API_KEY)
        
        # Initialize the model
        print(f"Testing model: {MODEL_NAME}")
        print("=" * 50)
        
        model = genai.GenerativeModel(MODEL_NAME)
        
        # Test prompt
        prompt = "Hello, what is your name?"
        
        print(f"\nPrompt: {prompt}")
        print("-" * 50)
        
        # Generate content
        response = model.generate_content(prompt)
        
        # Display response
        if response and response.text:
            print("\nGemini's Response:")
            print("-" * 50)
            print(response.text)
            print("-" * 50)
            print("\n✓ API test successful!")
            print(f"✓ Model '{MODEL_NAME}' is working correctly")
        else:
            print("\n✗ Received empty response")
            
    except Exception as e:
        print(f"\n✗ Error occurred: {type(e).__name__}")
        print(f"✗ Error message: {str(e)}")
        
        # Check if it's a model availability issue
        if "not found" in str(e).lower() or "invalid" in str(e).lower():
            print(f"\n⚠ Model '{MODEL_NAME}' may not be available.")
            print("⚠ Try using 'gemini-2.5-flash-lite' or 'gemini-1.5-flash' instead.")

if __name__ == "__main__":
    test_gemini_api()