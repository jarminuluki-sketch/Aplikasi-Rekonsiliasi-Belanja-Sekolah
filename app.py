import json
import io
import os
import requests
import pandas as pd
import pdfplumber
import streamlit as st
from datetime import datetime
from PIL import Image as PILImage
from supabase import create_client, Client

# ==========================================
# 1. KONFIGURASI HALAMAN & KONEKSI SUPABASE
# ==========================================
st.set_page_config(
    page_title="Aplikasi Rekonsiliasi Belanja Sekolah - Kab. Buol",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #fef9c3 0%, #dcfce7 50%, #fef08a 100%);
        background-attachment: fixed;
    }
    .running-text-box {
        background-color: rgba(255, 255, 255, 0.85);
        padding: 10px;
        border-radius: 12px;
        margin-bottom: 20px;
        border: 2px solid #16a34a;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_supabase() -> Client:
    try:
        url = "https://kmdggpfsrabkjlbztuq.supabase.co"
        key = "sb_publishable_OSF90--G5BnumFC2AKN2WQ_h8Zo5QMu"
        return create_client(url, key)
    except Exception as e:
        return None

supabase = init_supabase()

# ==========================================
# 2. HELPER FUNCTIONS (UPLOAD & PARSE)
# ==========================================
def upload_to_supabase_storage(file, bucket_name="dokumen-rekon", folder_prefix=""):
    if not supabase:
        st.error("Koneksi Supabase belum terhubung.")
        return None
    try:
        file.seek(0)
        file_bytes = file.read()
        filename = f"{folder_prefix}_{int(datetime.now().timestamp())}_{file.name.replace(' ', '_')}"
        path_on_supa = f"uploads/{filename}"
        
        supabase.storage.from_(bucket_name).upload(
            path=path_on_supa,
            file=file_bytes,
            file_options={"content-type": "application/pdf"}
        )
        return supabase.storage.from_(bucket_name).get_public_url(path_on_supa)
    except Exception as e:
        st.error(f"Gagal mengunggah berkas ke Storage: {e}")
        return None

def parse_pdf(file):
    file.seek(0)
    all_rows = []
    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if row and any(row):
                            all_rows.append(row)
        if not all_rows:
            return pd.DataFrame()
        df = pd.DataFrame(all_rows[1:], columns=all_rows[0])
        return df[df[df.columns[0]] != df.columns[0]]
    except Exception:
        return pd.DataFrame()

# ==========================================
# 3. MANAJEMEN SESSION LOGIN
# ==========================================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'user_info' not in st.session_state: st.session_state['user_info'] = {}

st.markdown("""
    <div class="running-text-box">
        <marquee behavior="scroll" direction="left" scrollamount="8" style="font-size: 20px; font-weight: bold; color: #15803d;">
            📢 Mari lakukan rekonsiliasi secara berkala dengan teliti dan disiplin. Data yang tertib menjadi dasar pelaporan yang akurat dan akuntabel!
        </marquee>
    </div>
""", unsafe_allow_html=True)

st.sidebar.title("🔐 Keamanan Sistem")

if not supabase:
    st.sidebar.error("⚠️ Koneksi DNS/Supabase Gagal (Name or service not known). Periksa koneksi internet atau jaringan Anda.")

if not st.session_state['logged_in']:
    st.sidebar.subheader("Silakan Login")
    username_input = st.sidebar.text_input("Username")
    password_input = st.sidebar.text_input("Password", type="password")
    
    if st.sidebar.button("Masuk"):
        clean_user = username_input.strip().lower()
        clean_pass = password_input.strip()
        
        if not clean_user or not clean_pass:
            st.sidebar.warning("Username dan Password tidak boleh kosong!")
        elif not supabase:
            st.sidebar.error("Tidak dapat masuk karena database belum terhubung.")
        else:
            try:
                res = supabase.table("users").select("*").eq("username", clean_user).execute()
                matched_user = res.data[0] if res.data else None
                
                if matched_user and str(matched_user.get('password', '')).strip() == clean_pass:
                    st.session_state['logged_in'] = True
                    st.session_state['user_info'] = {
                        'username': matched_user['username'],
                        'nama_sekolah': matched_user['nama_sekolah'],
                        'role': matched_user['role']
                    }
                    st.rerun()
                else:
                    st.sidebar.error("Username atau Password salah!")
            except Exception as e:
                st.sidebar.error(f"Gagal memproses login: {e}")
else:
    user = st.session_state['user_info']
    st.sidebar.success(f"Login sebagai:\n**{user['nama_sekolah']}**")
    st.sidebar.write(f"Role: `{user['role']}`")
    
    if st.sidebar.button("🚪 Logout / Keluar"):
        st.session_state['logged_in'] = False
        st.session_state['user_info'] = {}
        st.rerun()

# ==========================================
# 4. HALAMAN UTAMA APLIKASI
# ==========================================
st.title("📊 Aplikasi Rekonsiliasi Belanja Sekolah")
st.caption("Dinas Pendidikan dan Kebudayaan Kabupaten Buol")

if not st.session_state['logged_in']:
    st.info("👈 Silakan masukkan Username dan Password Anda di sidebar sebelah kiri untuk masuk.")
else:
    user = st.session_state['user_info']
    st.divider()

    # --- PANEL ADMIN ---
    if user['role'] == 'admin':
        st.subheader("👨‍💼 Panel Administrator Dinas Pendidikan")
        tab_verif, tab_users = st.tabs(["🔍 Verifikasi Laporan Sekolah", "👥 Manajemen Akun Pengguna"])

        with tab_verif:
            st.write("### Daftar Laporan Masuk dari Sekolah")
            data_rekon = []
            try:
                if supabase:
                    res_rekon = supabase.table("hasil_rekon").select("*").order("id", desc=True).execute()
                    data_rekon = res_rekon.data if res_rekon.data else []
            except Exception as e:
                st.error(f"Gagal memuat data: {e}")

            if data_rekon:
                df_p = pd.DataFrame(data_rekon)
                st.dataframe(df_p[['id', 'nama_sekolah', 'tanggal_submit', 'status']], use_container_width=True)
                
                selected_id = st.selectbox("Pilih ID Laporan untuk Diverifikasi:", options=df_p['id'].tolist())
                row_v = df_p[df_p['id'] == selected_id].iloc[0]
                
                st.info(f"**Sekolah:** {row_v['nama_sekolah']} | **Status:** `{row_v['status']}`")
                
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    if row_v.get('url_sipd'):
                        st.link_button("👁️ Buka Dokumen SIPD", row_v['url_sipd'])
                with col_d2:
                    if row_v.get('url_bank'):
                        st.link_button("👁️ Buka Dokumen BKU", row_v['url_bank'])

                with st.form(f"form_verif_{selected_id}"):
                    new_status = st.selectbox("Ubah Status Verifikasi:", ["Menunggu Verifikasi", "Disetujui", "Ditolak / Perlu Perbaikan"])
                    catatan = st.text_area("Catatan Admin:", value=row_v.get('catatan_admin', '') or '')
                    btn_simpan = st.form_submit_button("💾 Simpan Perubahan Status")

                    if btn_simpan:
                        try:
                            supabase.table("hasil_rekon").update({
                                'status': new_status,
                                'catatan_admin': catatan
                            }).eq("id", selected_id).execute()
                            st.success("Status berhasil diperbarui!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Gagal memperbarui: {e}")
            else:
                st.info("Belum ada laporan rekon yang dikirimkan sekolah.")

        with tab_users:
            st.write("### Tambah Akun Sekolah Baru")
            with st.form("add_user_form"):
                new_u = st.text_input("Username Baru")
                new_p = st.text_input("Password Baru", type="password")
                new_ns = st.text_input("Nama Sekolah / Instansi")
                new_r = st.selectbox("Role", ["sekolah", "admin"])
                btn_add = st.form_submit_button("Tambah Akun")

                if btn_add:
                    if new_u and new_p and new_ns:
                        try:
                            supabase.table("users").insert({
                                'username': new_u.lower().strip(),
                                'password': new_p.strip(),
                                'nama_sekolah': new_ns.strip(),
                                'role': new_r
                            }).execute()
                            st.success(f"Akun {new_ns} berhasil dibuat!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Gagal membuat akun: {e}")
                    else:
                        st.warning("Semua kolom harus diisi!")

    # --- PANEL SEKOLAH ---
    else:
        st.subheader(f"Panel Pengiriman Laporan: {user['nama_sekolah']}")
        tab_input, tab_hist = st.tabs(["📥 Unggah Dokumen Rekon", "📜 Riwayat Pengiriman"])

        with tab_input:
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                pdf_sipd = st.file_uploader("Upload File Realisasi Belanja (SIPD (.pdf))", type=["pdf"])
            with col_u2:
                pdf_bank = st.file_uploader("Upload File Catatan BKU / ARKAS (.pdf))", type=["pdf"])

            if pdf_sipd and pdf_bank:
                st.success("Kedua file PDF berhasil diunggah dan siap diproses!")
                if st.button("🚀 Kirim Laporan Rekonsiliasi"):
                    with st.spinner("Mengunggah dokumen ke server..."):
                        url_sipd = upload_to_supabase_storage(pdf_sipd, folder_prefix=f"{user['username']}_sipd")
                        url_bank = upload_to_supabase_storage(pdf_bank, folder_prefix=f"{user['username']}_bku")

                        if url_sipd and url_bank:
                            payload = {
                                'username': user['username'],
                                'nama_sekolah': user['nama_sekolah'],
                                'tanggal_submit': datetime.now().strftime("%Y-%m-%d %H:%M"),
                                'status': 'Menunggu Verifikasi',
                                'url_sipd': url_sipd,
                                'url_bank': url_bank,
                                'catatan_admin': ''
                            }
                            try:
                                supabase.table("hasil_rekon").insert(payload).execute()
                                st.success("Laporan berhasil dikirim ke Dinas Pendidikan!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal menyimpan ke database: {e}")

        with tab_hist:
            st.write("### Riwayat Pengiriman Anda")
            hist_data = []
            try:
                if supabase:
                    res_h = supabase.table("hasil_rekon").select("*").eq("username", user['username']).execute()
                    hist_data = res_h.data if res_h.data else []
            except Exception as e:
                st.error(f"Gagal memuat riwayat: {e}")

            if hist_data:
                st.dataframe(pd.DataFrame(hist_data)[['id', 'tanggal_submit', 'status', 'catatan_admin']], use_container_width=True)
            else:
                st.info("Anda belum memiliki riwayat pengiriman.")
