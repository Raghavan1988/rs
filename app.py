# deep_research_reddit.py
# ─────────────────────────────────────────────────────────────────────────────
# Streamlit assistant for genre‑based Reddit deep research tailored for
# screen‑writers and producers.
# Includes password protection and report download options (.txt and .pdf).
# ─────────────────────────────────────────────────────────────────────────────

import os, json, time, random, io
from datetime import datetime, timezone
from typing import List, Dict, Callable
from unidecode import unidecode

import streamlit as st
from dotenv import load_dotenv
import openai
import praw
from fpdf import FPDF

# ── PASSWORD PROTECTION ─────────────────────────────────────────────────────
st.set_page_config(page_title="Reddit Research", layout="centered")

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    pwd = st.text_input("Password", type="password")
    if st.button("Submit"):
        if pwd in {"raghavan", "Abiriscool123!"}:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()

# ── CSS: Verdana 14 pt everywhere ────────────────────────────────────────────
st.markdown(
    """
    <style>
    html, body, [class*="css"], .stMarkdown, .stTextInput, .stButton, .stSlider label {
        font-family: Verdana, sans-serif !important;
        font-size: 14px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── ENV / KEYS ───────────────────────────────────────────────────────────────
load_dotenv()
openai.api_key        = os.getenv("OPENAI_API_KEY", "")
REDDIT_CLIENT_ID      = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET  = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT     = os.getenv("REDDIT_USER_AGENT", "DeepResearch/0.1")

if not all([openai.api_key, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET]):
    st.error("🚨 Set your OpenAI & Reddit credentials via env‑vars or a .env file.")
    st.stop()

# ── REDDIT CLIENT ────────────────────────────────────────────────────────────
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT,
)

# ── Helpers ──────────────────────────────────────────────────────────────────
GENRE_DEFAULT_SUB = {
    "horror": "horror",
    "sci-fi": "scifi",
    "rom-com": "romcom",
    "superhero": "marvelstudios",
    "documentary": "documentaries",
    "animation": "animation",
    "crime": "TrueFilm",
    "thriller": "Thrillers",
}

def fetch_threads(sub: str, limit: int, timer_cb: Callable[[], None]) -> List[Dict]:
    threads = []
    for post in reddit.subreddit(sub).new(limit=limit):
        post.comments.replace_more(limit=None)
        comments = " ".join(c.body for c in post.comments.list())
        threads.append({
            "id": post.id,
            "title": post.title,
            "body": post.selftext or "",
            "comments": comments,
            "url": post.url,
            "created": datetime.fromtimestamp(post.created_utc, tz=timezone.utc).strftime("%Y-%m-%d"),
        })
        timer_cb()
    return threads

def summarise_threads(threads: List[Dict], progress_bar, status_slot, sample_slot, timer_cb: Callable[[], None], model: str = "o3", batch: int = 6) -> None:
    total = len(threads)
    done = 0
    for i in range(0, total, batch):
        chunk = threads[i:i + batch]
        payload = {
            t["id"]: f"{t['title']}\n\n{t['body'][:4000]}\n\nComments:\n{t['comments'][:6000]}"
            for t in chunk
        }
        status_slot.markdown(f"**Summarising:** {chunk[0]['title'][:80]}…")
        sample_thread = random.choice(threads)
        sample_slot.markdown(f"*Random thread:* **{sample_thread['title'][:90]}**")

        msgs = [
            {
                "role": "system",
                "content": (
                    "You are a research summarizer. Infer what redditors are saying in the thread. Summarize so that it would be easy for a mid career professional with AI/ML background working at big tech. For each Reddit thread JSON {id:text} return JSON with keys "
                    "gist (50 words), insight1, insight2, sentiment (positive/neutral/negative)."
                ),
            },
            {"role": "user", "content": json.dumps(payload)},
        ]
        resp = openai.chat.completions.create(model=model, messages=msgs)
        summaries = json.loads(resp.choices[0].message.content)
        for t in chunk:
            t["summary"] = summaries.get(t["id"], {})
        done += len(chunk)
        progress_bar.progress(done / total)
        timer_cb()
        time.sleep(0.5)
    status_slot.markdown("**Summarising complete!**")

def generate_report(genre: str, threads: List[Dict], questions: List[str], timer_cb: Callable[[], None]) -> str:
    corpus = "\n\n".join(
        f"{t['title']} – {t['summary'].get('gist','')} [URL]({t['url']})" for t in threads
    )[:15000]

    q_block = "\n".join(f"Q{i+1}. {q}" for i, q in enumerate(questions))

    prompt = (
        "You are an analyst assisting a mid career professional, an AI engineer currently an Engineering manager, honing their craft; advancing their career. "
        f"**{genre.title()}** genre. You have mined Reddit audience discussions. "
        "First, give a one‑paragraph snapshot of overall audience sentiment for this subreddit. "
        "Then, answer each research question in its own subsection (≤2 paragraphs each), call out any FIRST principles that the reader should know "
        "adding citations in [Title](URL) form right after every key evidence point. "
        "Finish with a bold **list of ACTIONABLE INSIGHTS**: 3 points for surviving in the AI era, especially as a mid-career Engineering Manager in Big tech industry."
    )

    msgs = [
        {"role": "system", "content": prompt},
        {"role": "assistant", "content": f"CORPUS ({len(threads)} threads):\n{corpus}"},
        {"role": "user", "content": q_block},
    ]
    resp = openai.chat.completions.create(model="o3", messages=msgs)
    timer_cb()
    return resp.choices[0].message.content

# ── UI ──────────────────────────────────────────────────────────────────────
st.title("🎬 Subreddit Reddit Audience Intel  - Deep Research Agent that can mine subreddits and answer your questions")

ticker = st.sidebar.empty()
start_time = time.time()
def tick():
    elapsed = time.time() - start_time
    mins, secs = divmod(int(elapsed), 60)
    ticker.write(f"⏱️ {mins:02d}:{secs:02d}")

col1, col2 = st.columns([2, 1])
with col1:
    genre_input = st.text_input("field", value="klaviyo").strip().lower()
with col2:
    n_posts = st.slider("Threads", 10, 200, 50, step=10)

subreddit = st.text_input("Subreddit").strip()

st.markdown("#### Research questions (1‑5, one per line)")
qs_text = st.text_area("Questions", "What is the general sentiment on Klaviyo? ", label_visibility="collapsed")
questions = [q.strip() for q in qs_text.splitlines() if q.strip()][:5]

if st.button("Run research 🚀"):
    if not subreddit:
        st.error("Please specify a subreddit.")
        st.stop()
    if not questions:
        st.error("Enter at least one research question.")
        st.stop()

    with st.spinner("⛏️ Fetching threads + comments…"):
        threads = fetch_threads(subreddit, n_posts, tick)

    progress = st.progress(0.0)
    status = st.empty()
    sample_preview = st.empty()
    with st.spinner("📝 Summarising…"):
        summarise_threads(threads, progress, status, sample_preview, tick)

    st.success(f"Summarised {len(threads)} threads from r/{subreddit}.")
    with st.expander("🔍 Gists & insights"):
        st.json([{"title": t["title"], **t["summary"], "url": t["url"]} for t in threads])

    with st.spinner("🧠 Crafting final report…"):
        report_md = generate_report(genre_input, threads, questions, tick)

    st.markdown("## 📊 Audience‑Driven Report")
    st.markdown(report_md)

    # ── DOWNLOAD OPTIONS ─────────────────────────────────────────────────────
    st.markdown("## 📥 Download Report")

    # Text download
    txt_buf = io.StringIO()
    txt_buf.write(report_md)
    st.download_button("📄 Download as .txt", txt_buf.getvalue(), file_name="reddit_research_report.txt", mime="text/plain")

    # PDF download
    from unidecode import unidecode
    class PDF(FPDF):
        def header(self):
            self.set_font("Arial", "B", 12)
            self.cell(0, 10, "Reddit Research Report", ln=True, align="C")
        
        def footer(self):
            self.set_y(-15)
            self.set_font("Arial", "I", 8)
            self.cell(0, 10, f"Page {self.page_no()}", align="C")
        def chapter_body(self, text):
            self.set_font("Arial", "", 11)
            try:
                self.multi_cell(0, 7, unidecode(text))  # ✅ Fixes UnicodeEncodeError
            except:
                self.multi_cell(0,7,"Exception")


    pdf = PDF()
    pdf.add_page()
    pdf.chapter_body(report_md)
    pdf_output = io.BytesIO()
    pdf.output(pdf_output)
    st.download_button("📘 Download as .pdf", data=pdf_output.getvalue(), file_name="reddit_research_report.pdf", mime="application/pdf")

    from fpdf import FPDF
    from unidecode import unidecode
    class PDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 12)
            self.cell(0, 10, "Reddit Research Report", new_x="LMARGIN", new_y="NEXT", align="C")
        def footer(self):
            self.set_y(-15)
            self.set_font("Helvetica", "I", 8)
            self.cell(0, 10, f"Page {self.page_no()}", align="C")
            
            
        def build_pdf(text: str) -> bytes:
            """
            Convert markdown/plain-text string to PDF and return **raw bytes**
            ready for st.download_button.
            """
            pdf = PDF()
            pdf.set_auto_page_break(auto=True, margin=15)
            pdf.add_page()
            pdf.set_font("Helvetica", size=11)
            pdf.multi_cell(0, 7, unidecode(text))
            # FPDF.output(dest="S") returns a **latin-1 encoded str** → convert to bytes
            return pdf.output(dest="S").encode("latin-1")
    pdf_bytes = build_pdf(report_md)
    st.download_button("📘 Download as .pdf", data=pdf_bytes, file_name="reddit_research_report.pdf",mime="application/pdf",)

    tick()
