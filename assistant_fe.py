import os
import streamlit as st
from openai import OpenAI
import time
import requests
import json
from langchain_community.chat_message_histories import (
    StreamlitChatMessageHistory,
)
api_key = st.secrets["openai_api_key"]
assistant_id = st.secrets["assistant_id"]

st.set_page_config(page_title="Reddit Scraper Chatbot", layout="centered")
st.title("Reddit Scraper Chatbot")

def create_new_thread(client):
    new_thread = client.beta.threads.create() 
    print("NEW THREAD CREATED: ", new_thread.id)
    return new_thread

@st.cache_resource
def load_openai_client_and_assistant():
    client = OpenAI(api_key=api_key)
    my_assistant = client.beta.assistants.retrieve(assistant_id)
    # thread = client.beta.threads.retrieve(thread_id)
    new_thread = create_new_thread(client)
    
    return client, my_assistant, new_thread

client, my_assistant, assistant_thread = load_openai_client_and_assistant()

def extract_and_format_citations(messages):
    responses_with_citations = []
    for msg in messages:
        if msg.role == "assistant":
            text = msg.content[0].text.value
            annotations = msg.content[0].text.annotations
            
            for annotation in annotations:
                if annotation.type == "file_citation":
                    citation_text = annotation.text
                    # citation_detail = annotation.file_citation.quote
                    print("CITATION TEXT: ", citation_text)
                    # print("CITATION DETAIL: ",citation_detail)
                    # TODO: Implement citation hover. 
                    # citation_replace = "\nCitation: '" + citation_detail + "'"
                    # UPDATE (03/05/24): not working from OPENAI's end, removing the annotation 
                    text = text.replace(citation_text, "")
            responses_with_citations.append(text)
    return responses_with_citations

def wait_on_run(run, thread):
    if(run.status == "failed"):
        return st.markdown(run.last_error.message)
    while run.status == "queued" or run.status == "in_progress":
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id,
        )
        time.sleep(0.5)
    return run

def get_assistant_response(user_prompt, file_id):
    # print("fileID in get_assistance_response: ",file_id)
    message = client.beta.threads.messages.create(
        thread_id=assistant_thread.id,
        role="user",
        content=user_prompt,
        attachments=[{'file_id':file_id,'tools':[{'type':'file_search'}]}]
        
    )
    run = client.beta.threads.runs.create(
        thread_id=assistant_thread.id,
        assistant_id=assistant_id,
    )

    run = wait_on_run(run, assistant_thread)
    if(run.status == "failed"):
        return run.last_error.message
    else:
        messages = client.beta.threads.messages.list(
            thread_id=assistant_thread.id, order="asc", after=message.id
        )
        # print("MESSAGE: ", messages)
        assistant_responses = [msg.content[0].text.value for msg in messages.data if msg.role == "assistant"]
        
        #TODO: Fix Citations
        assistant_responses_citations = extract_and_format_citations(messages)

        return assistant_responses_citations

def get_response(user_prompt, file_id):
    # print("fileID in get_response: ",file_id)
    response = get_assistant_response(user_prompt, file_id)
    return response

def clear_input_field():
    st.session_state.user_question = st.session_state.user_input
    st.session_state.user_input = ""

def set_send_input():
    st.session_state.send_input = True
    clear_input_field()

def clear_url_field():
    st.session_state.reddit_url = st.session_state.reddit_url_input
    st.session_state.reddit_url_input = ""
def set_reddit_url_input():
    st.session_state.reddit_url_input = True
    clear_url_field()

def delete_thread_and_file(thread_id, file_id):
    response = client.beta.threads.delete(thread_id)
    print("OPENAI THREAD DELETE RESPONSE: ",response)
    response = client.files.delete(file_id)
    print("OPENAI FILE DELETE RESPONSE: ",response)    
    
    # if 'file_id' in st.session_state:
    #     del st.session_state['file_id']

    local_file_name = "redditContent.txt"
    if os.path.exists(local_file_name):
        os.remove(local_file_name)
        print("LOCAL TXT FILE DELETED SUCCESSFULLY")
    else:
        print("LOCAL TXT FILE DOES NOT EXIST")

def clear_chat (file_id):
    print("CLEARING CHAT")
    delete_thread_and_file(assistant_thread.id, file_id)

    # chat_history.clear()
    st.session_state.messages = []
    st.warning("Chat cleared successfully!")
    time.sleep(1)
    st.cache_resource.clear()
    st.rerun()

# Gets reddit thread in JSON format and uploads it 
# as a file to OpenAI. Returns id of uploaded file
def get_reddit_thread_json(url):
    if url:
        # Remove trailing slash if present
        if url.endswith('/'):
            url = url[:-1]

        # Attach ".json" to the URL
        modified_url = f"{url}.json"

        # print the modified URL
        print("Modified URL:", modified_url)

        try:
            # Fetch the JSON object from the modified URL
            response = requests.get(modified_url)
            response.raise_for_status()  # Raise an HTTPError for bad responses

            # Get the JSON content
            json_content = response.json()

            # Convert JSON object to string
            json_str = json.dumps(json_content, indent=4)

            # Save the JSON content to a .txt file
            with open('redditContent.txt', 'w') as file:
                file.write(json_str)

            try:
                response = client.files.create(
                    file=open("redditContent.txt", "rb"),
                    purpose="assistants"
                )
                print ("Uploaded file successfully to OpenAI: ", response.id)
                file_id = response.id
                st.success("JSON content fetched and successfully uploaded to OpenAI.")
                return file_id
            except Exception as e:
                st.error("Error uploading file to OpenAI: ", e)
                return None
        except requests.exceptions.RequestException as e:
            st.error(f"Error fetching Reddit thread: {e}")
            return None


def main():
    if "reddit_url_input" not in st.session_state:
        st.session_state.reddit_url_input= False
        st.session_state.reddit_url= ""
    if "file_id" not in st.session_state:
        st.session_state.file_id = ""
    # Input element to accept a URL from the user
    reddit_url = st.text_input("Enter the  URL", key="reddit_url")
    get_json_btn = st.button("Get Reddit thread")
    if(get_json_btn):
        st.session_state.file_id = get_reddit_thread_json(reddit_url)
        # print("fileID in session state = ",st.session_state.file_id)
     
    chat_container = st.container()    
    if "send_input" not in st.session_state:
        st.session_state.send_input = False
        st.session_state.user_question = ""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    # chat_history = StreamlitChatMessageHistory(key="history")
    user_input = st.text_input("Type your message here", key="user_input", on_change=set_send_input)
    col1, col2 = st.columns([1,7])
    with col1:
        send_button = st.button("Send", key="send_button", disabled=st.session_state.file_id == None)
    if send_button or st.session_state.send_input:
        if st.session_state.user_question != "" :
            with chat_container:
                # st.chat_message("user").write(st.session_state.user_question)
                # chat_history.add_user_message(st.session_state.user_question)
                st.session_state.messages.append({"role":"user","content": st.session_state.user_question})
                with st.chat_message("user"):
                    st.markdown(st.session_state.user_question)
                response = get_response(st.session_state.user_question, st.session_state.file_id)
                for responses in response:
                    # st.chat_message("ai").write(responses)
                    # chat_history.add_ai_message(responses)
                    st.session_state.messages.append({"role":"assistant","content": responses})
                    with st.chat_message("assistant"):
                        st.markdown(responses)
                st.session_state.user_question = ""
    # # print(chat_history.messages)
    # if chat_history.messages != []:
    #     with chat_container:
    #         st.write("Chat history: ")
    #         for message in chat_history.messages:
    #             st.chat_message(message.type).write(message.content)
    # clear_chat_button_disabled = len(chat_history.messages) == 0
    clear_chat_button_disabled = len(st.session_state.messages) == 0
    if not clear_chat_button_disabled:
        with col2:
            with st.popover("Clear Chat"):
                st.write("Are you sure you want to clear the chat?")
                confirmation = st.button ("Confirm Clear")
                if confirmation:
                    clear_chat(st.session_state.file_id)


if __name__ == '__main__':
    main()