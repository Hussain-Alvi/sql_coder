# gradio_ui.py
import gradio as gr
import requests

API_URL = "http://127.0.0.1:8000"

# ---------- endpoint wrappers ----------
def call_generate_sql(user_input, session_id=""):
    payload = {"user_input": user_input, "session_id": session_id or None}
    r = requests.post(f"{API_URL}/generate-sql", json=payload)
    return r.json()

def call_export_schema():
    r = requests.get(f"{API_URL}/export-schema")
    return r.json()

def call_create_session():
    r = requests.post(f"{API_URL}/sessions")
    return r.json()

def call_list_sessions():
    r = requests.get(f"{API_URL}/sessions")
    return r.json()

def call_get_session(session_id):
    r = requests.get(f"{API_URL}/sessions/{session_id}")
    return r.json()

def call_delete_session(session_id):
    r = requests.delete(f"{API_URL}/sessions/{session_id}")
    return r.json()

def call_delete_all_sessions():
    r = requests.delete(f"{API_URL}/sessions")
    return r.json()

def call_get_history():
    r = requests.get(f"{API_URL}/history")
    return r.json()

# ---------- Gradio UI ----------
with gr.Blocks(title="SQLCoder API Tester") as demo:
    gr.Markdown("## SQLCoder — Test all FastAPI endpoints via UI")

    with gr.Tab("Generate SQL"):
        user_input = gr.Textbox(label="User Input", lines=3)
        session_input = gr.Textbox(label="Session ID (optional)")
        gen_btn = gr.Button("Generate SQL + Execute")
        gen_output = gr.JSON(label="Response")
        gen_btn.click(call_generate_sql, [user_input, session_input], gen_output)

    with gr.Tab("Schema"):
        schema_btn = gr.Button("Export Schema")
        schema_output = gr.JSON(label="Schema Export Response")
        schema_btn.click(call_export_schema, None, schema_output)

    with gr.Tab("Sessions"):
        with gr.Row():
            create_btn = gr.Button("Create Session")
            create_out = gr.JSON(label="Create Session Response")
            create_btn.click(call_create_session, None, create_out)

        with gr.Row():
            list_btn = gr.Button("List Sessions")
            list_out = gr.JSON(label="List Sessions Response")
            list_btn.click(call_list_sessions, None, list_out)

        with gr.Row():
            sess_id_in = gr.Textbox(label="Session ID")
            get_btn = gr.Button("Get Session History")
            get_out = gr.JSON(label="Session History Response")
            get_btn.click(call_get_session, sess_id_in, get_out)

        with gr.Row():
            del_id_in = gr.Textbox(label="Session ID to Delete")
            del_btn = gr.Button("Delete Session")
            del_out = gr.JSON(label="Delete Session Response")
            del_btn.click(call_delete_session, del_id_in, del_out)

        with gr.Row():
            del_all_btn = gr.Button("Delete All Sessions")
            del_all_out = gr.JSON(label="Delete All Sessions Response")
            del_all_btn.click(call_delete_all_sessions, None, del_all_out)

    with gr.Tab("History"):
        hist_btn = gr.Button("Get All History")
        hist_out = gr.JSON(label="History Response")
        hist_btn.click(call_get_history, None, hist_out)

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860)
