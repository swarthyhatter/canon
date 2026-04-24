import os

import streamlit as st
from bonfires import BonfiresClient
from dotenv import load_dotenv

from harmonica.client import HarmonicaClient
import store.db as db


@st.cache_resource
def get_clients():
    load_dotenv()
    db.init()
    bonfire = BonfiresClient(
        api_key=os.environ["BONFIRE_API_KEY"],
        bonfire_id=os.environ["BONFIRE_ID"],
        agent_id=os.environ["BONFIRE_AGENT_ID"],
    )
    harmonica = HarmonicaClient()
    return bonfire, harmonica
