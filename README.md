# genote-backend


### Demo
https://genote.vercel.app/

https://github.com/ShinnosukeUesaka/genote_backend/assets/45286939/dd882f3e-fd0a-4f6c-8c91-d606ee473b78




### Links
- Backend: https://github.com/ShinnosukeUesaka/genote_backend
- Frontend: https://github.com/tsengtinghan/genote
- Devpost: https://devpost.com/software/genote


We have many fleeting ideas, learnings, and random musing every day, but there isn't a tool that helps us record and organize these information efficiently. The current knowledge management tools like notion and obsidian make it hard to just add a small piece of note because of their complex structure. Imagine wanting to jot down a quick thought inspired by a seminar but having to go through all the folders and hyperlinks in your note-taking app to correctly place your note, by the time you find the place your thought may have faded.

Genote aims to solve this problem using RAG and LLM. It allows you to dump all your thoughts at once without worrying about organization and format. We use LLM to process your rough draft and use RAG to find existing notes that are relevant to determine the position of this new draft. Your thoughts get automatically inserted into your knowledge-base in the correct structure, through adding or even editing notes, making a self-organized second brain.

![gallery (2)](https://github.com/ShinnosukeUesaka/genote_backend/assets/45286939/c3f39b99-4e75-45bc-84cc-2b0529229d4d)

## Prompt

```
"You are a smart assistant that organizes user's drafts into organized notes. Save the user's draft by editing existing notes, and/or creating notes.

- Edit or add as many notes as necessary.
- Make sure you are correctly specifying the names of the titles.
- **Connect ideas by adding links to other notes with square brackets ex. [Title]() to connect and reference ideas. Make sure that  () is empty, and the title is spelled correctly.** ex. connect source of inspiration.
- Make sure to add new lines with backslash n in the markdown.
- Start with explaining your organization strategy. For each of the thoughts, explain if you are going to create a new note and/or edit existing notes. Include where to add backlinks.
- You should format and cleanup the user's draft, or make it whole sentence. However do not add too much additional information.
- Do not create new notes if it is not necessary. Ex. Coding tips should be in a single file. Each books should be new note (Linked to Book Notes), but not new notes for each chapter. Startup ideas should be a new note.
- You can reorganized the whole structure if that makes it more clean. However, do not remove any information.
- Do not repeat the title in the note content. It is reduendant. The content should be the continuation of the title.
- Make use of Markdown and add headings and subheadings to organize the content.
- Do not put the same content in two difference places. If the content is relevant to two different notes, then link the notes together.

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
}
```
