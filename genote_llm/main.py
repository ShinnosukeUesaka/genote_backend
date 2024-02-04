import dotenv

dotenv.load_dotenv('genote_llm/.env', override=True)
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
# from elevenlabs import set_api_key
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Optional
from icrawler.builtin import GoogleImageCrawler

# set_api_key(os.environ.get("XI_API_KEY"))

client = OpenAI()



app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


    
class DraftInput(BaseModel):
    text: str
    
class NoteInput(BaseModel):
    title: str
    content: str
# test endpoint
@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/users/{user_id}/notes")
def read_notes(user_id: str, skip: int = 0, limit: int = 10):
    notes = db.collection("users").document(user_id).collection("notes").stream()
    return [{"id": note.id, "data": note.to_dict()} for note in notes]

@app.post("/users/{user_id}/notes")
def add_notes(user_id: str, note_input: NoteInput):
    note = db.collection("users").document(user_id).collection("notes").add({"title": note_input.title, "content": note_input.content})
    return note[1].id

@app.get("/users/{user_id}/notes/{note_id}")
def read_notes(user_id: str, note_id: str):
    note = db.collection("users").document(user_id).collection("notes").document(note_id).get()
    return note.to_dict()

@app.post("/users/{user_id}/draft")
def add_notes(user_id: str, draft_input: DraftInput):
    # get all the notes of the user
    draft = draft_input.text.strip()
    notes_stream = db.collection("users").document(user_id).collection("notes").stream()
    # Do RAG here.
    notes = [{"id": note.id, "data": note.to_dict()} for note in notes_stream]
    actions = create_actions(draft, notes)
    for action in actions:
        if action["method"] == "edit":
            note = next((note for note in notes if note["data"]["title"] == action["title"]), None)
            if not note:
                print("Note not found creating new one.")
                note = db.collection("users").document(user_id).collection("notes").add({"title": action["title"], "content": action["content"], "status": "draft"})
            else:
                note = db.collection("users").document(user_id).collection("notes").document(note["id"])
                note.update({"content": action["content"]})
        else:
            note = db.collection("users").document(user_id).collection("notes").add({"title": action["title"], "content": action["content"]})


CHOOSE_NOTES_PROMPT = """You are a smart assistant that organizes user's drafts into organized notes. Save the user's draft by either editing existing notes, creating notes.

- If you are editing the current note, specify the title exactly as you see above.
- If you are creating a new note, specify the title of the new note. Try to follow the naming convention of the existing notes.
- Edit or add as many notes as necessary.

Output must be json that follows the following schema. Output should not be the schema itself, but the json object that follows the schema.

{
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "method": { 
                        "type": "string",
                        "enum": ["edit", "add"]
                    },
                    "title": {
                        "type": "string"
                    }
                }
            }
        }
    }
}
"""

ORGANIZE_NOTES_PROMPT = """You are a smart assistant that organizes user's drafts into organized notes. Save the user's draft by editing existing notes, and/or creating notes.

- Edit or add as many notes as necessary.
- Make sure you are correctly specifying the names of the titles.
- Connect ideas by adding links to other notes with square brackets ex. [Title of the note] to connect and reference ideas.  Start by concisely explaining how ideas in the user's draft can be linked together in less than 2 sentences.
- The link should be bidirectional , meaning both ideas should reference each other. Not just one.
- Make sure to add new lines with backslash n in the markdown.

You output should be json that follows the following schema. Output should not be the schema itself, but the json object that follows the schema.
{
    "type": "object",
    "properties": {
        "link_explanation": {"type": "string"}
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "method": { 
                        "type": "string",
                        "enum": ["edit", "add"]
                    },
                    "title": {
                        "type": "string"
                    },
                    "content": {
                        "type": "string",
                        "format": "markdown",
                        "description": "The full markdown containing added contents and original contents."
                    }
                }
            }
        }
    }
}"""

def create_actions(draft: str, notes: list[dict]):
    titles_prompt = ""
    for index, note in enumerate(notes):
        titles_prompt += f"{index+1}. {note['data']['title']}\n"
    
    user_prompt = f"""[User's Draft]
""
{draft}
""

[Notes that are potentially relevant to the user's draft]
{titles_prompt}
"""
    print(user_prompt) 
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": CHOOSE_NOTES_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=2000,
    )
    result = response.choices[0].message.content # this is json in string
    returned_dictionary =  json.loads(result)
    print(returned_dictionary)
    
    notes_list_prompt = ""
    current_notes_prompt = ""
    for action in returned_dictionary["actions"]:
        if action["method"] == "edit":
            edit_note = next((note for note in notes if note["data"]["title"] == action["title"]), None)
            if not edit_note:
                print("Note not found creating new one.")
                action["content"] = "add"
                notes_list_prompt += f"- {action['title']} [Add]\n"
                
            else:
                notes_list_prompt += f"- {action['title']} [Edit]\n"
                current_notes_prompt += f"""{action['title']}
""
{edit_note['content']}
""

""" 
        else:
            notes_list_prompt += f"- {action['title']} [Add]\n"
        
    user_prompt = f"""[user's draft]
""
{draft}
""

[Notes you can add or edit]
{notes_list_prompt}

[Current data of the notes]
{current_notes_prompt}
"""
    print(user_prompt)
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": ORGANIZE_NOTES_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=2000,
    )
    result = response.choices[0].message.content # this is json in string
    returned_dictionary =  json.loads(result)
    print(returned_dictionary)
    return returned_dictionary["actions"]


        


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


if __name__ == "__main__":
    print(create_actions("I went to school", [{"id": "1", "data": {"title": "School", "content": "I went to school"}}]))
