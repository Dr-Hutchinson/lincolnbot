import pandas as pd
import msgpack
import streamlit as st

@st.cache_data(persist="disk")
def load_lincoln_speech_corpus():
    with open('/mnt/data/lincoln_speech_corpus.msgpack', 'rb') as f:
        unpacker = msgpack.Unpacker(f, raw=False)
        data = [unpacked for unpacked in unpacker]

        # Ensure data is not empty
        if not data:
            raise ValueError("The data is empty. Ensure the msgpack file is formatted correctly.")

        # Check the structure of the first element
        first_item = data[0]

        # Log the type of first_item
        st.write(f"Type of first item: {type(first_item)}")

        # If it's a list, unpack the first dictionary
        if isinstance(first_item, list) and len(first_item) > 0 and isinstance(first_item[0], dict):
            first_item = first_item[0]

        # Log the keys of the first dictionary
        if isinstance(first_item, dict):
            st.write(f"Keys of first dictionary item: {list(first_item.keys())}")
        else:
            raise ValueError("The data structure is not as expected. Ensure the msgpack file is formatted correctly.")

        # Flatten the data: from columns to list of dictionaries
        flat_data = [first_item[str(i)] for i in range(len(first_item))]
        return flat_data

@st.cache_data(persist="disk")
def load_voyant_word_counts():
    with open('/mnt/data/voyant_word_counts.msgpack', 'rb') as f:
        unpacker = msgpack.Unpacker(f, raw=False)
        data = [unpacked for unpacked in unpacker]
        return data[0]

@st.cache_data(persist="disk")
def load_lincoln_index_embedded():
    return pd.read_parquet('/mnt/data/lincoln_index_embedded.parquet')
