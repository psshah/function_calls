from dotenv import load_dotenv
import chainlit as cl
from movie_functions import get_now_playing_movies, get_showtimes, buy_ticket, get_reviews
import json
import re

load_dotenv()

# Note: If switching to LangSmith, uncomment the following, and replace @observe with @traceable
# from langsmith.wrappers import wrap_openai
# from langsmith import traceable
# client = wrap_openai(openai.AsyncClient())

from langfuse.decorators import observe
from langfuse.openai import AsyncOpenAI

client = AsyncOpenAI()

gen_kwargs = {
    "model": "gpt-4o",
    "temperature": 0.2,
    "max_tokens": 500
}

SYSTEM_PROMPT = """\
You are a virtual assistant who has the capability to provide a user information about movies, showtimes and possible help them book tickets.

For list current movies requests, use the following function call format:
{"function": "get_now_playing_movies", "parameters": {}}

To get showtimes for a movie, use the following function call format:
{"function": "get_showtimes", "parameters": {"title": "title", "location": "location"}}

After receiving the results of a function call, incorporate that information into your response to the user.
"""

@observe
@cl.on_chat_start
def on_chat_start():
    message_history = [{"role": "system", "content": SYSTEM_PROMPT}]
    cl.user_session.set("message_history", message_history)

@observe
async def generate_response(client, message_history, gen_kwargs):
    response_message = cl.Message(content="")
    await response_message.send()

    stream = await client.chat.completions.create(messages=message_history, stream=True, **gen_kwargs)
    async for part in stream:
        if token := part.choices[0].delta.content or "":
            await response_message.stream_token(token)

    await response_message.update()

    return response_message

@cl.on_message
@observe
async def on_message(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])
    message_history.append({"role": "user", "content": message.content})

    response_message = await generate_response(client, message_history, gen_kwargs)

    # Check if the response contains get_now_playing_movies
    if "get_now_playing_movies" in response_message.content:
        try:
            result = get_now_playing_movies()
            message_history.append({"role": "user", "content": result})
            response_message = await generate_response(client, message_history, gen_kwargs)
        except Exception as e:
            print(f"Error calling get_now_playing_movies: {e}")
    # Check if the response contains get_showtimes
    if "get_showtimes" in response_message.content:
        print("get_showtimes")
        print(response_message.content)

        try:
            # Parse the function call
            json_pattern = r'\{[^{}]*\}'
            # Find the JSON object in the input string
            match = re.search(json_pattern, response_message.content)
            if match:
                json_string = match.group()
                print("json is " + json_string)

                # Parse the JSON string
                data = json.loads(json_string)
                print(data)
                # Extract title and location from the parameters
                title = data['title']
                location = data['location']

                print(f"Title: {title}")
                print(f"Location: {location}")
                if title and location:
                    result = get_showtimes(title, location)
                    message_history.append({"role": "user", "content": result})
                    response_message = await generate_response(client, message_history, gen_kwargs)
                else:
                    print("Missing title or location for get_showtimes")
            else:
                    print("No JSON object found in the input string")
        except json.JSONDecodeError:
            print("Error parsing JSON")
        except KeyError:
            print("Required keys not found in the JSON data")

    message_history.append({"role": "assistant", "content": response_message.content})
    cl.user_session.set("message_history", message_history)

if __name__ == "__main__":
    cl.main()
