import dotenv

dotenv.load_dotenv('genote/.env', override=True)
from pathlib import Path
from fastapi import FastAPI, Header
from urllib.parse import urlencode

from pydantic import BaseModel
from openai import Client, OpenAI
from typing import Annotated
from starlette.middleware.cors import CORSMiddleware
from tempfile import TemporaryDirectory


import os
import datetime
from genote_llm.firebase_utils import db, bucket
import uuid
import json
from elevenlabs import generate, play
from elevenlabs import set_api_key
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Optional
from icrawler.builtin import GoogleImageCrawler

set_api_key(os.environ.get("XI_API_KEY"))

client = OpenAI()



app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    message: str

# test endpoint
@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/conversations")
def create_conversation():
    # create id
    conversation_id = str(uuid.uuid4())
    # create conversation
    conversation = {
        "id": conversation_id,
        "created_at": datetime.datetime.now(),
        "messages": [],
    }
    # save conversation
    db.collection("conversations").document(conversation_id).set(conversation)
    return conversation

@app.post("/conversations/{conversation_id}/message")
def create_message(conversation_id: str, message: Message):
    # get conversation
    message = message.message
    conversation_ref = db.collection("conversations").document(conversation_id)
    conversation = conversation_ref.get().to_dict()
    conversation["messages"].append({"role": "user", "content": message})
    past_messages = conversation["messages"]
    # generate slides
    result, actions = create_slides(past_messages)
    conversation["messages"].append({"role": "assistant", "content": result})
    conversation_ref.set(conversation)
    return actions



PROMPT = """You are an assistant that would provide information to the user in a presentation style. You are an assistant so you do not need any greeting.

Generate scripts and presentation slides based on the question of the user.

Choose a template, and fill the information in the components.

Each of the components in the slides have a component id. In the script, include the component id when the component needs to be displayed to the user. In the beginning, none of the components are rendered.
Example of the script)
[title, sub-title] I will explain the history of spaceships. [bullet-point-1]  The development of space ships started in....

Other Instruction:
For images on the slides, write 3 keywords. The keywords would be used to search an image online.
Use variety of templates.

Your answer must follow the following json format.



{
    "type": "object",
    "properties": {
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "template": {
                        "anyOf": [
                            {
                                "properties": {
                                    "template_id": {
                                        "const": "first_slide"
                                    },
                                    "title": {
                                        "type": "string",
                                        "description": "id: title"
                                    },
                                    "sub_title": {
                                        "type": "string",
                                        "description": "id: sub_title"
                                    },
                                    "image": {
                                        "type": "string",
                                        "description": "Prompt for the image\nid: image\n"
                                    }
                                },
                                "required": [
                                    "template_id",
                                    "title",
                                    "sub_title",
                                    "image"
                                ]
                            },
                            {
                                "properties": {
                                    "template_id": {
                                        "const": "three_elements"
                                    },
                                    "title": {
                                        "type": "string",
                                        "description": "id: title"
                                    },
                                    "elements": {
                                        "type": "array",
                                        "minItems": 3,
                                        "maxItems": 3,
                                        "description": "id: element_element_index. ex) element_1\ntitles and details would be displayed using this id.  index starts from 1",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "title": {
                                                    "type": "string"
                                                },
                                                "details": {
                                                    "type": "string",
                                                    "description": "Two short sentences."
                                                }
                                                "image": {
                                                    "type": "string",
                                                    "description": "Prompt for the image\nid: image\n"
                                                }
                                            },
                                            "required": [
                                                "title",
                                                "details",
                                                "image"
                                            ]
                                        }
                                    }
                                },
                                "required": [
                                    "template_id",
                                    "title",
                                    "elements"
                                ]
                            },
                            {
                                "properties": {
                                    "template_id": {
                                        "const": "timeline"
                                    },
                                    "title": {
                                        "type": "string",
                                        "description": "id: title"
                                    },
                                    "elements": {
                                        "type": "array",
                                        "minItems": 3,
                                        "maxItems": 3,
                                        "description": "id: element_element_index. ex) element_1\ntitles and details would be displayed using this id. index starts from 1",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "title": {
                                                    "type": "string"
                                                },
                                                "time": {
                                                    "type": "string",
                                                    "description": "ex. 2019"
                                                },
                                                "details": {
                                                    "type": "string",
                                                    "description": "Under 7 words"
                                                }
                                            },
                                            "required": [
                                                "title",
                                                "time",
                                                "details"
                                            ]
                                        }
                                    }
                                }
                            }
                        ],
                        "type": "object"
                    },
                    "script": {
                        "type": "string"
                    }
                },
                "required": [
                    "template",
                    "script"
                ]
            }
        }
    },
    "required": [
        "slides"
    ]
}"""

def create_slides(past_messages: list = []):
    
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": PROMPT},
        ] + past_messages,
        max_tokens=2000,
    )
    result = response.choices[0].message.content # this is json in string
    # parse json 
    returned_dictionary =  json.loads(result)
    
    actions = []
    for slide in returned_dictionary["slides"]:
        if slide["template"]["template_id"] == "first_slide":
            slide["template"]["image"] = generate_image(slide["template"]["image"])
        elif slide["template"]["template_id"] == "three_elements":
            for index, element in enumerate(slide["template"]["elements"]):
                slide["template"]["elements"][index]["image"] = generate_image(element["image"])
                
        actions.append(
            {
                "type": "show_slide",
                "content": slide["template"]
            }
        )
        # split script by [element-id]
        script_elements = format_script(slide["script"])
        for element in script_elements:
            if isinstance(element, str):
                actions.append(
                    {
                        "type": "play_audio",
                        "content": {"url": create_tts(element)}
                    }
                )
            else:
                # if there is , in the element, it means there are multiple elements, split
                actions.append(
                    {
                        "type": "display_element",
                        "content": {
                            "ids": element
                        }
                    }
                )
    return result, actions

def format_script(input_text):
    # Split the input text on markers, keeping the markers
    parts = input_text.split('[')
    formatted_output = []

    for part in parts:
        if ']' in part:
            marker, text = part.split(']', 1)
            # Add the marker as a list
            marker = marker.strip()
            if "," in marker:
                formatted_output.append(marker.split(","))
            else:
                formatted_output.append([marker.strip()])
            # Add the text if it's not empty
            text = text.strip()
            if text:
                formatted_output.append(text)
        elif part:
            # Add the part if it's not empty
            formatted_output.append(part.strip())

    return formatted_output


def generate_image(prompt: str):
    # used crawler to get the image
    try:
        crawler = GoogleImageCrawler(
            downloader_threads=4,
            # use path from current file
            storage={'root_dir': os.path.join(os.path.dirname(__file__), 'images')})
        crawler.crawl(
            keyword=prompt,
            max_num=1,
            file_idx_offset=0)
        # get file in the folder
        folder_path =  os.path.join(os.path.dirname(__file__), 'images')
        file_path = os.path.join(folder_path, os.listdir(folder_path)[0])
        # upload to firebase
        id = str(uuid.uuid4())
        blob = bucket.blob(f'images/{id}.jpg')
        blob.upload_from_filename(file_path)
        blob.make_public()
        url = blob.public_url
        # delete the file
        os.remove(file_path)
    except:
        url = "https://storage.googleapis.com/slidesllm.appspot.com/images/f7718626-3511-4297-a2bb-0c33ac381c8b.jpg"
        
    return url
    
def create_tts(text: str, voice: str = "Bill", model: str = "eleven_turbo_v2"):

    audio: bytes = generate(
        text=text,
        voice=voice,
        model=model,
    )

    # save the audio in firestore storage and make it public
    with TemporaryDirectory() as temp_dir:
        audio_path = Path(temp_dir) / "audio.mp3"
        with open(audio_path, "wb") as f:
            f.write(audio)
        audio_path = str(audio_path)
        id = str(uuid.uuid4())
        blob = bucket.blob(f'audio/{id}.mp3')
        blob.upload_from_filename(audio_path)
        blob.make_public()
        url = blob.public_url
    return url
