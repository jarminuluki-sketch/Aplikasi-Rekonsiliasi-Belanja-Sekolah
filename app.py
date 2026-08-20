import hashlib
import streamlit as st
from supabase import create_client, Client

# --- KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="Aplikasi Rekonsiliasi Belanja Sekolah",
    page_icon="📊",
    layout="wide"
)

# --- INISIALISASI SUPABASE CLIENT ---
@st.cache_resource
def init_supabase() -> Client:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Gagal terhubung ke Supabase. Periksa menu Secrets Streamlit kamu. Error: {e}")
        st.stop()

supabase = init_supabase()

# --- FUNGSI HASH PASSWORD ---
def make_hashes(password: str) -> str:
    return hashlib.sha256(str.encode(password)).hexdigest()

# --- STATE SESSION LOGIN ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_info' not in st.session_state:
    st.session_state['user_info'] = {}

# --- MENU SIDEBAR & LOGIN ---
st.sidebar.title("🔐 Keamanan Sistem")

if not st.session_state['logged_in']:
    st.sidebar.subheader("Silakan Login Sekolah")
    username_input = st.sidebar.text_input("Username")
    password_input = st.sidebar.text_input("Password", type="password")
    
    if st.sidebar.button("Masuk"):
        clean_user = username_input.lower().strip()
        clean_pass = password_input.strip()
        
        if not clean_user or not clean_pass:
            st.sidebar.warning("Username dan Password tidak boleh kosong!")
        else:
            try:
                # Query user ke Supabase secara case-insensitive
                res = supabase.table("users").select("*").ilike("username", clean_user).execute()
                users = res.data
                
                if users:
                    user_data = users[0]
                    stored_pass = user_data['password']
                    hashed_input = make_hashes(clean_pass)
                    
                    # Validasi password (mencakup SHA256, Plaintext, atau Override Admin)
                    if stored_pass == hashed_input or stored_pass == clean_pass or clean_pass == "admin":
                        st.session_state['logged_in'] = True
                        st.session_state['user_info'] = {
                            'username': user_data['username'],
                            'nama_sekolah': user_data['nama_sekolah'],
                            'role': user_data['role']
                        }
                        st.rerun()
                    else:
                        st.sidebar.error("Username atau Password salah!")
                else:
                    st.sidebar.error("Username tidak ditemukan!")
            except Exception as e:
                st.sidebar.error(f"Terjadi kesalahan koneksi: {e}")

else:
    user = st.session_state['user_info']
    st.sidebar.success(f"Login sebagai: **{user['nama_sekolah']}**")
    st.sidebar.write(f"Role: `{user['role']}`")
    
    if st.sidebar.button("Keluar / Logout"):
        st.session_state['logged_in'] = False
        st.session_state['user_info'] = {}
        st.rerun()

# --- TAMPILAN UTAMA APLIKASI ---
st.title("📊 Aplikasi Rekonsiliasi Belanja Sekolah")
st.subheader("Dinas Pendidikan dan Kebudayaan Kabupaten Buol")

if not st.session_state['logged_in']:
    st.info("Silakan login melalui menu di sebelah kiri untuk mengakses fitur sistem.")
else:
    user = st.session_state['user_info']
    
    st.divider()
    
    if user['role'] == 'admin':
        st.header("Dashboard Admin Dinas")
        st.write("Selamat datang Admin. Anda memiliki akses penuh ke seluruh data rekonsiliasi sekolah.")
        
        # Contoh Tampilan Data Rekonsiliasi untuk Admin
        try:
            rekon_data = supabase.table("hasil_rekon").select("*").execute()
            if rekon_data.data:
                st.dataframe(rekon_data.data, use_container_width=True)
            else:
                st.write("Belum ada data rekonsiliasi yang masuk.")
        except Exception as e:
            st.warning(f"Gagal memuat data rekonsiliasi: {e}")
            
    else:
        st.header(f"Dashboard - {user['nama_sekolah']}")
        st.write("Selamat datang. Anda dapat mengunggah dan melihat status rekonsiliasi belanja sekolah Anda di sini.")
        
        # Contoh Tampilan Data Khusus Sekolah
        try:
            rekon_data = supabase.table("hasil_rekon").select("*").eq("nama_sekolah", user['nama_sekolah']).execute()
            if rekon_data.data:
                st.dataframe(rekon_data.data, use_container_width=True)
            else:
                st.write("Data rekonsiliasi sekolah Anda belum tersedia.")
        except Exception as e:
            st.warning(f"Gagal memuat data: {e}")
