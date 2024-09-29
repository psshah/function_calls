from dotenv import load_dotenv
import chainlit as cl
from prompts import SYSTEM_PROMPT, REVIEW_SYSTEM_PROMPT
from movie_functions import get_now_playing_movies, get_showtimes, buy_ticket, get_reviews, confirm_ticket_purchase
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

def parse_json(response_message):
    try:
        json_pattern = r'\{[^{}]*\}'

        # Find the JSON object in the input string
        match = re.search(json_pattern, response_message)
        if match:
            json_string = match.group()
            print("json is " + json_string)

            # Parse the JSON string
            data = json.loads(json_string)
            print(data)
            return data
        else:
            print("No JSON object found in the input string")
    except json.JSONDecodeError:
        print("Error parsing JSON")
    except KeyError:
        print("Required keys not found in the JSON data")
    return None


async def fetch_reviews(message_history):
    temp_message_history = message_history.copy()
    temp_message_history[0] = {"role": "system", "content": REVIEW_SYSTEM_PROMPT}
    temp_message_history.append({"role": "system", "content": REVIEW_SYSTEM_PROMPT})

    response_message = await client.chat.completions.create(messages=temp_message_history, **gen_kwargs)

    response_message = response_message.choices[0].message.content

    #response_message = await generate_response(client, message_history, gen_kwargs)
    print("Review response is " + response_message)
    data = parse_json(response_message)
    if data:
        movie_id = data['id']
        print(f"movie id: {movie_id}")
        if movie_id:
            reviews = get_reviews(movie_id)
            message_history.append({"role": "system", "content": rf"CONTEXT: {reviews}"})
        else:
            print("Missing movie id for get_reviews")

@cl.on_message
@observe
async def on_message(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])
    message_history.append({"role": "user", "content": message.content})

    await fetch_reviews(message_history)

    response_message = await generate_response(client, message_history, gen_kwargs)
    #print(response_message.content)

    message_history.append({"role": "assistant", "content": response_message.content});
    cl.user_session.set("message_history", message_history)

    # Check if the response contains get_now_playing_movies
    function_called = True
    while function_called:
        if "get_now_playing_movies" in response_message.content:
            function_called = True
            try:
                result = get_now_playing_movies()
                message_history.append({"role": "user", "content": result})
                response_message = await generate_response(client, message_history, gen_kwargs)
            except Exception as e:
                print(f"Error calling get_now_playing_movies: {e}")
        # Check if the response contains get_showtimes
        elif "get_showtimes" in response_message.content:
            function_called = True
            # Extract title and location from the parameters
            data = parse_json(response_message.content)
            if data:
                title = data['title']
                location = data['location']

                print(f"Title: {title} Location: {location}")
                if title and location:
                    result = get_showtimes(title, location)
                    message_history.append({"role": "user", "content": result})
                    response_message = await generate_response(client, message_history, gen_kwargs)
                else:
                    print("Missing title or location for get_showtimes")
        elif "buy_ticket" in response_message.content:
            function_called = True
            data = parse_json(response_message.content)
            if data:
                # Extract title and location from the parameters
                theater = data['theater']
                movie = data['movie']
                showtime = data['showtime']
                print(f"Theater: {theater} movie: {movie} showtime: {showtime}")

                if theater and movie and showtime:
                    result = buy_ticket(theater, movie, showtime)
                    message_history.append({"role": "user", "content": result})
                    response_message = await generate_response(client, message_history, gen_kwargs)
                else:
                    print("Missing theater, movie or showtime for buy_ticket")
        elif "confirm_ticket_purchase" in response_message.content:
            function_called = True
            data = parse_json(response_message.content)
            if data:
                # Extract title and location from the parameters
                theater = data['theater']
                movie = data['movie']
                showtime = data['showtime']
                print(f"Theater: {theater} movie: {movie} showtime: {showtime}")

                if theater and movie and showtime:
                    result = confirm_ticket_purchase(theater, movie, showtime)
                    message_history.append({"role": "user", "content": result})
                    response_message = await generate_response(client, message_history, gen_kwargs)
                else:
                    print("Missing theater, movie or showtime for confirm_ticket_purchase")
        else:
            function_called = False

    message_history.append({"role": "assistant", "content": response_message.content})
    cl.user_session.set("message_history", message_history)

if __name__ == "__main__":
    cl.main()
