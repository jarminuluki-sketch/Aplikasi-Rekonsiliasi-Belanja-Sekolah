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
        clean_user = username_input.strip().lower()
        clean_pass = password_input.strip()
        
        if not clean_user or not clean_pass:
            st.sidebar.warning("Username dan Password tidak boleh kosong!")
        else:
            try:
                # 1. Ambil semua data users untuk pencocokan langsung
                res = supabase.table("users").select("*").execute()
                all_users = res.data if res.data else []
                
                # Cek jika tabel users di Supabase benar-benar kosong, otomatis buatkan akun admin
                if not all_users:
                    supabase.table("users").insert({
                        'username': 'admin',
                        'password': 'admin',
                        'nama_sekolah': 'Admin Dinas Pendidikan',
                        'role': 'admin'
                    }).execute()
                    res = supabase.table("users").select("*").execute()
                    all_users = res.data if res.data else []

                # Cari user yang cocok (abaikan huruf besar/kecil & spasi)
                matched_user = None
                for u in all_users:
                    if str(u.get('username', '')).strip().lower() == clean_user:
                        matched_user = u
                        break
                
                if matched_user:
                    stored_pass = str(matched_user.get('password', ''))
                    hashed_input = make_hashes(clean_pass)
                    
                    # Verifikasi Password (Plaintext, SHA256, atau Kata Kunci 'admin')
                    if stored_pass == clean_pass or stored_pass == hashed_input or clean_pass == "admin":
                        st.session_state['logged_in'] = True
                        st.session_state['user_info'] = {
                            'username': matched_user['username'],
                            'nama_sekolah': matched_user['nama_sekolah'],
                            'role': matched_user['role']
                        }
                        st.rerun()
                    else:
                        st.sidebar.error("Password tidak sesuai!")
                else:
                    st.sidebar.error(f"Username '{clean_user}' tidak ditemukan!")
            except Exception as e:
                st.sidebar.error(f"Terjadi kesalahan koneksi: {e}")

    st.sidebar.markdown("---")
    # Tombol Darurat untuk Membuka Akses Langsung
    if st.sidebar.button("🛠️ Masuk Langsung Sebagai Admin (Bypass)"):
        st.session_state['logged_in'] = True
        st.session_state['user_info'] = {
            'username': 'admin',
            'nama_sekolah': 'Admin Dinas Pendidikan',
            'role': 'admin'
        }
        st.rerun()

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
        st.success("Akses berhasil terbuka!")
        st.write("Anda dapat mengelola akun sekolah dan melihat data laporan rekonsiliasi yang masuk.")
        
        # Tampilkan Daftar Akun Terdaftar dari Supabase
        st.subheader("📋 Daftar Akun Terdaftar di Supabase")
        try:
            res_users = supabase.table("users").select("id, username, nama_sekolah, role").execute()
            if res_users.data:
                st.dataframe(res_users.data, use_container_width=True)
            else:
                st.write("Belum ada data user di tabel.")
        except Exception as e:
            st.warning(f"Gagal mengambil data user: {e}")
            
    else:
        st.header(f"Dashboard - {user['nama_sekolah']}")
        st.write("Selamat datang. Anda dapat mengunggah dan melihat status rekonsiliasi belanja sekolah Anda di sini.")
