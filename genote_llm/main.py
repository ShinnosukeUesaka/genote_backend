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
import re

from genote_llm.firebase_utils import db, bucket
from genote_llm.rag import add_notes_to_rag, get_notes_most_relevant, update_note_to_rag

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

class InitialNote(BaseModel):
    title: str
    content: str
    order: int
    
class InitialNotesInput(BaseModel):
    notes: list[InitialNote]
    
    
class LoginInput(BaseModel):
    email: str
    password: str

# test endpoint
@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/users")
def create_user(inital_notes_input: InitialNotesInput):
    user_id = str(uuid.uuid4())
    user_ref = db.collection("users").document(user_id)
    user_ref.set({"created_at": datetime.datetime.now()})
    initial_notes = inital_notes_input.notes
    notes = []
    for note in initial_notes:
        note = user_ref.collection("notes").add({"title": note.title, "content": note.content, "status": "reviewed", "order": note.order})[1].get()
        notes.append({"id": note.id, "data": note.to_dict()})
    add_notes_to_rag(notes)
    return user_id

@app.post("/login")
def login_user(login_input: LoginInput):
    # find user with field email == email, if it exists return the user_id, if not create a new user
    users = db.collection("users").where("email", "==", login_input.email).get()
    if len(users) == 0:
        user_id = str(uuid.uuid4())
        user_ref = db.collection("users").document(user_id)
        user_ref.set({"created_at": datetime.datetime.now(), "email": login_input.email})
        return user_id
    else:
        return users[0].id

@app.get("/users/{user_id}/notes")
def read_notes(user_id: str, skip: int = 0, limit: int = 10):

    notes = db.collection("users").document(user_id).collection("notes").stream()
    return [{"id": note.id, "data": note.to_dict()} for note in notes]
x
@app.put("/users/{user_id}/notes/{note_id}")
def update_notes(user_id: str, note_id: str, note_input: NoteInput):
    note = db.collection("users").document(user_id).collection("notes").document(note_id)
    note.update({"title": note_input.title, "content": note_input.content})
    return {"id": note_id, "data": note.to_dict()}

@app.get("/users/{user_id}/notes/from-title/{title}")
def read_notes(user_id: str, title: str):
    notes = db.collection("users").document(user_id).collection("notes").where("title", "==", title).get()
    note = notes[0]
    return note.id

@app.post("/users/{user_id}/notes")
def add_notes(user_id: str, note_input: NoteInput):
    note = db.collection("users").document(user_id).collection("notes").add({"title": note_input.title, "content": note_input.content})[1].get()
    note = {"id": note.id, "data": note.to_dict()}
    return note[1].id

def get_notes_in_order(user_id: str):
    notes_stream = db.collection("users").document(user_id).collection("notes").order_by("order").stream()
    notes = [{"id": note.id, "data": note.to_dict()} for note in notes_stream]
    notes_in_oder = []
    
    for note in notes:
        if note["data"]["status"] == "added":
            notes_in_oder.append(note)
            db.collection("users").document(user_id).collection("notes").document(note["id"]).update({"order": len(notes_in_oder)})
    
    for note in notes:
        if note["data"]["status"] == "edited":
            notes_in_oder.append(note)
            db.collection("users").document(user_id).collection("notes").document(note["id"]).update({"order": len(notes_in_oder)})
    
    for note in notes:
        if note["data"]["status"] == "reviewed":
            notes_in_oder.append(note)
            db.collection("users").document(user_id).collection("notes").document(note["id"]).update({"order": len(notes_in_oder)})
    return notes_in_oder

@app.post("/users/{user_id}/notes/{note_id}/review")
def review_notes(user_id: str, note_id: str):
    note = db.collection("users").document(user_id).collection("notes").document(note_id)
    note.update({"status": "reviewed"})
    return get_notes_in_order(user_id)

@app.get("/users/{user_id}/notes/{note_id}")
def read_notes(user_id: str, note_id: str):
    note = db.collection("users").document(user_id).collection("notes").document(note_id).get()
    return note.to_dict()

@app.post("/users/{user_id}/draft")
def add_notes(user_id: str, draft_input: DraftInput):
    # get all the notes of the user
    draft = draft_input.text.strip()
    notes_stream = db.collection("users").document(user_id).collection("notes").stream()
    note_ids = get_notes_most_relevant(draft, top_k=5)
    print(note_ids)
    # fix note ids
    notes = [{"id": note.id, "data": note.to_dict()} for note in notes_stream]
    actions = create_actions(draft, notes)
    for index, action in enumerate(actions):
        # search for [title], then replace with [title](id), id is the firebase id of the note
        content = action["content"]
        # search [title] in the content
        titles = re.findall(r'\[.*?\]', content) # titles is 
        for title in titles:
            title_text = title[1:-1]
            note = next((note for note in notes if note["data"]["title"] == title_text), None)
            if note:
                content = content.replace(title, f"{title}({note['id']})")
        actions[index]["content"] = content
             
         
    
    for action in actions:
        if action["method"] == "edit":
            note = next((note for note in notes if note["data"]["title"] == action["title"]), None)
            if not note:
                print("Note not found creating new one.")
                note = db.collection("users").document(user_id).collection("notes").add({"title": action["title"], "content": action["content"], "status": "added", "order": -2})[1].get()
                add_notes_to_rag([{"id": note.id, "data": note.to_dict()}])
            else:
                note = db.collection("users").document(user_id).collection("notes").document(note["id"])
                note.update({"content": action["content"], "status": "edited", "order": -1})
                note = note.get()
                update_note_to_rag({"id": note.id, "data": note.to_dict()})
        elif action["method"] == "add":
            note = db.collection("users").document(user_id).collection("notes").add({"title": action["title"], "content": action["content"], "status": "added", "order": -2})[1].get()
            add_notes_to_rag([{"id": note.id, "data": note.to_dict()}])
        else:
            print("Invalid action")
    
    return get_notes_in_order(user_id)
    


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

# ORGANIZE_NOTES_PROMPT = """You are a smart assistant that organizes user's drafts into organized notes. Save the user's draft by editing existing notes, and/or creating notes.

# - Edit or add as many notes as necessary.
# - Make sure you are correctly specifying the names of the titles.
# - Connect ideas by adding links to other notes with square brackets ex. [Title of the note] to connect and reference ideas.  Start by concisely explaining how ideas in the user's draft can be linked together in less than 2 sentences.
# - The link should be bidirectional , meaning both ideas should reference each other. Not just one.
# - Make sure to add new lines with backslash n in the markdown.

# You output should be json that follows the following schema. Output should not be the schema itself, but the json object that follows the schema.
# {
#     "type": "object",
#     "properties": {
#         "link_explanation": {"type": "string"}
#         "actions": {
#             "type": "array",
#             "items": {
#                 "type": "object",
#                 "properties": {
#                     "method": { 
#                         "type": "string",
#                         "enum": ["edit", "add"]
#                     },
#                     "title": {
#                         "type": "string"
#                     },
#                     "content": {
#                         "type": "string",
#                         "format": "markdown",
#                         "description": "The full markdown containing added contents and original contents."
#                     }
#                 }
#             }
#         }
#     }
# }"""

ORGANIZE_NOTES_PROMPT = """You are a smart assistant that organizes user's drafts into organized notes. Save the user's draft by editing existing notes, and/or creating notes.

- Edit or add as many notes as necessary.
- Make sure you are correctly specifying the names of the titles.
- **Connect ideas by adding links to other notes with square brackets ex. [Title]() to connect and reference ideas. Make sure that  () is empty, and the title is spelled correctly.** ex. connect source of inspiration.
- Make sure to add new lines with backslash n in the markdown.
- Start with explaining your organization strategy. For each of the thoughts, explain if you are going to create a new note and/or edit existing notes. Include where to add backlinks.
- You should format and cleanup the user's draft, or make it whole sentence. However do not add too much additional information.
- Do not create new notes if it is not necessary. Ex. Coding tips should be in a single file. Each books should be new note (Linked to Book Notes), but not new notes for each chapter. Startup ideas should be a new note.
- You can reorganized the whole structure if that makes it more clean. However, do not remove any information.
- Do not repeat the title in the note content.

You output should be json that follows the following schema. Output should NOT be the schema itself, but the json object that follows the schema. Start with {"organization_explanation": "explanation here", "actions": [...
{
    "type": "object",
    "properties": {
        "organization_explanation": {"type": "string"}
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
#     titles_prompt = ""
#     for index, note in enumerate(notes):
#         titles_prompt += f"{index+1}. {note['data']['title']}\n"
    
#     user_prompt = f"""[User's Draft]
# ""
# {draft}
# ""

# [Notes that are potentially relevant to the user's draft]
# {titles_prompt}
# """
#     print(user_prompt) 
#     response = client.chat.completions.create(
#         model="gpt-4-1106-preview",
#         response_format={ "type": "json_object" },
#         messages=[
#             {"role": "system", "content": CHOOSE_NOTES_PROMPT},
#             {"role": "user", "content": user_prompt}
#         ],
#         max_tokens=2000,
#     )
#     result = response.choices[0].message.content # this is json in string
#     returned_dictionary =  json.loads(result)
#     print(returned_dictionary)
    
    current_notes_prompt = ""
    for note in notes:
        current_notes_prompt += f"""{note["data"]['title']}
""
{note["data"]['content']}
""


""" 


    user_prompt = f"""[user's draft]
""
{draft}
""

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
    print(create_actions("I went to school", [{"id": "1", "data": {"title": "School", "content": "I went to school today it was fun."}}]))
