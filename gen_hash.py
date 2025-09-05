import streamlit_authenticator as stauth
import streamlit as st

st.title("Generador de hash para contraseña")

password = st.text_input("Contraseña que quieres usar", type="password")
if password:
    hash_pw = stauth.Hasher([password]).generate()[0]
    st.write("Copia este hash para tu config:")
    st.code(hash_pw)