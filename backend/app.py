import os
import sqlite3
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import pdfplumber
import docx
from sentence_transformers import SentenceTransformer, util
import torch
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
CORS(app)

MODEL_NAME = "all-MiniLM-L6-v2"
model = SentenceTransformer(MODEL_NAME)
CHUNK_SIZE = 100  # words per chunk

DB_FILE = "plagiarism.db"

# --- Database setup ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL
                 )''')
    conn.commit()
    conn.close()

init_db()

# --- Text extraction ---
def extract_text_from_pdf(file_path):
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

def extract_text_from_docx(file_path):
    doc = docx.Document(file_path)
    text = ""
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

def extract_text_from_request(uploaded_file):
    filename = uploaded_file.filename
    ext = filename.split('.')[-1].lower()
    os.makedirs("temp", exist_ok=True)
    file_path = os.path.join("temp", filename)
    uploaded_file.save(file_path)

    if ext == "pdf":
        text = extract_text_from_pdf(file_path)
    elif ext == "docx":
        text = extract_text_from_docx(file_path)
    elif ext in ["txt", "text"]:
        text = uploaded_file.read().decode("utf-8")
    else:
        return None, "Unsupported file type"
    return text, None

# --- Utility ---
def split_text_into_chunks(text, chunk_size=CHUNK_SIZE):
    words = text.split()
    chunks = [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
    return chunks

def fetch_all_texts():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT text FROM documents")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def save_text(text):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO documents (text) VALUES (?)", (text,))
    conn.commit()
    conn.close()

def calculate_similarity(new_text):
    new_chunks = split_text_into_chunks(new_text)
    similarity_results = []

    stored_texts = fetch_all_texts()

    for stored_text in stored_texts:
        stored_chunks = split_text_into_chunks(stored_text)
        for i, new_chunk in enumerate(new_chunks):
            new_embedding = model.encode(new_chunk, convert_to_tensor=True)
            for j, stored_chunk in enumerate(stored_chunks):
                stored_embedding = model.encode(stored_chunk, convert_to_tensor=True)
                sim_score = util.pytorch_cos_sim(new_embedding, stored_embedding).item()
                if sim_score > 0.5:
                    similarity_results.append({
                        "new_chunk_index": i,
                        "stored_chunk_index": j,
                        "similarity": round(sim_score, 2),
                        "new_text": new_chunk,
                        "stored_text": stored_chunk
                    })
    return similarity_results

def generate_pdf_report(text, similarity_results, filename="report.pdf"):
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica", 12)
    y = height - 40

    c.drawString(40, y, f"Plagiarism Report")
    y -= 30
    c.drawString(40, y, f"Total chunks plagiarized: {len(similarity_results)}")
    y -= 30

    for res in similarity_results:
        if y < 100:
            c.showPage()
            c.setFont("Helvetica", 12)
            y = height - 40
        c.drawString(40, y, f"New Chunk {res['new_chunk_index']}: Similarity {res['similarity']}")
        y -= 20
        snippet = res['new_text'][:200].replace("\n", " ")
        c.drawString(60, y, f"Text: {snippet}...")
        y -= 30

    c.save()
    return filename

# --- API endpoint ---
@app.route("/check", methods=["POST"])
def check_plagiarism():
    if 'file' in request.files:
        uploaded_file = request.files['file']
        text, error = extract_text_from_request(uploaded_file)
        if error:
            return jsonify({"error": error}), 400
    else:
        data = request.json
        text = data.get("text")
        if not text:
            return jsonify({"error": "No text or file provided"}), 400

    similarity_results = calculate_similarity(text)
    save_text(text)
    plagiarism_percentage = round((len(similarity_results) / max(1, len(split_text_into_chunks(text)))) * 100, 2)

    pdf_filename = generate_pdf_report(text, similarity_results)

    return jsonify({
        "status": "success",
        "plagiarism_percentage": plagiarism_percentage,
        "similarity_details": similarity_results,
        "report_file": pdf_filename
    })

@app.route("/download-report/<filename>", methods=["GET"])
def download_report(filename):
    path = os.path.join(os.getcwd(), filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return jsonify({"error": "File not found"}), 404

if __name__ == "__main__":
    app.run(debug=True, port=5000)
