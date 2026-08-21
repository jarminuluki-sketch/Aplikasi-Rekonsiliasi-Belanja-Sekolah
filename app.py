import json
import io
import os
import requests
from io import BytesIO
import pandas as pd
import pdfplumber
import streamlit as st
from datetime import datetime
from PIL import Image as PILImage
from supabase import create_client, Client

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# --- KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="Aplikasi Rekonsiliasi Belanja Sekolah - Kab. Buol",
    page_icon="📊",
    layout="wide"
)

# --- INJEKSI CSS CUSTOM (BACKGROUND KUNING-HIJAU & FOOTER STYLE) ---
st.markdown("""
    <style>
    /* Background layar utama gradasi warna Kuning (Emas) ke Hijau khas Logo */
    .stApp {
        background: linear-gradient(135deg, #fef9c3 0%, #dcfce7 50%, #fef08a 100%);
        background-attachment: fixed;
    }

    /* Style untuk Kotak Running Text */
    .running-text-box {
        background-color: rgba(255, 255, 255, 0.85);
        padding: 10px;
        border-radius: 12px;
        margin-bottom: 20px;
        border: 2px solid #16a34a;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    /* Style Footer */
    .footer-container {
        margin-top: 50px;
        padding: 20px;
        background-color: rgba(255, 255, 255, 0.9);
        border-top: 3px solid #15803d;
        border-radius: 10px 10px 0 0;
        text-align: center;
        color: #14532d;
    }
    .footer-spirit {
        font-size: 20px;
        font-weight: bold;
        color: #15803d;
        margin-bottom: 5px;
    }
    .footer-copyright {
        font-size: 13px;
        color: #4b5563;
    }
    </style>
""", unsafe_allow_html=True)

# --- INISIALISASI SUPABASE ---
@st.cache_resource
def init_supabase() -> Client:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Gagal terhubung ke Supabase. Periksa Secrets Streamlit Anda. Error: {e}")
        st.stop()

supabase = init_supabase()

# --- HELPER KONVERSI TANGGAL BAHASA INDONESIA ---
def get_tanggal_indonesia_terbilang(dt=None):
    if not dt:
        dt = datetime.now()
    
    hari_map = {
        'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu',
        'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu', 'Sunday': 'Minggu'
    }
    bulan_map = {
        1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni',
        7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
    }
    
    hari = hari_map.get(dt.strftime('%A'), dt.strftime('%A'))
    tanggal = dt.day
    bulan = bulan_map.get(dt.month, '')
    tahun = dt.year
    
    return hari, str(tanggal), bulan, str(tahun)

# --- HELPER PARSING PDF ---
def parse_pdf(file):
    all_rows = []
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

def auto_detect_columns(df):
    tgl_col, nom_col, ket_col, ang_col = None, None, None, None
    for col in df.columns:
        col_lower = str(col).lower()
        if not tgl_col and any(k in col_lower for k in ['tgl', 'tanggal', 'date']):
            tgl_col = col
        elif not nom_col and any(k in col_lower for k in ['realisasi', 'nominal', 'jumlah', 'nilai', 'pengeluaran']):
            nom_col = col
        elif not ket_col and any(k in col_lower for k in ['uraian', 'keterangan', 'deskripsi', 'nama akun', 'kegiatan']):
            ket_col = col
        elif not ang_col and any(k in col_lower for k in ['anggaran', 'pagu', 'alokasi']):
            ang_col = col

    cols = list(df.columns)
    if not tgl_col and len(cols) > 0: tgl_col = cols[0]
    if not nom_col and len(cols) > 1: nom_col = cols[1]
    if not ket_col and len(cols) > 2: ket_col = cols[2]
    if not ang_col and len(cols) > 3: ang_col = cols[3]
    return tgl_col, nom_col, ket_col, ang_col

# --- GENERATE PDF BAR DENGAN FORMAT BIODATA PEJABAT ---
def generate_bar_pdf(sekolah_name, tanggal_submit_str, detail_items, status_rekon, biodata_sekolah=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []

    try:
        dt_obj = datetime.strptime(tanggal_submit_str, "%Y-%m-%d %H:%M")
    except:
        dt_obj = datetime.now()
        
    hari_str, tgl_str, bln_str, thn_str = get_tanggal_indonesia_terbilang(dt_obj)

    if not biodata_sekolah:
        biodata_sekolah = {
            'nama': '-', 'nip': '-', 'pangkat': '-', 'jabatan': 'Bendahara / Operator Sekolah', 'unit_kerja': sekolah_name
        }

    # Kop Surat
    header_text = [
        Paragraph("PEMERINTAH KABUPATEN BUOL", ParagraphStyle('H1', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=13, alignment=1)),
        Paragraph("DINAS PENDIDIKAN DAN KEBUDAYAAN", ParagraphStyle('H2', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=14, alignment=1)),
        Paragraph("Alamat : Jl. Batalipu Kel. Leok II Kecamatan Biau - Kode Pos : 94563", ParagraphStyle('H3', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=1))
    ]

    logo_img = None
    logo_path = "logo.png"
    logo_url = "https://i.ibb.co.com/zTtKR1f5/logo-png.png"

    if os.path.exists(logo_path):
        try:
            pil_img = PILImage.open(logo_path)
            img_byte_arr = BytesIO()
            pil_img.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            logo_img = RLImage(img_byte_arr, width=50, height=60)
        except Exception:
            logo_img = None

    if not logo_img:
        try:
            res = requests.get(logo_url, timeout=5)
            if res.status_code == 200:
                img_data = BytesIO(res.content)
                logo_img = RLImage(img_data, width=50, height=60)
        except Exception:
            logo_img = None

    if logo_img:
        header_table_data = [[logo_img, header_text]]
        header_table = Table(header_table_data, colWidths=[60, 490])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ]))
        story.append(header_table)
    else:
        for text_item in header_text:
            story.append(text_item)

    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.black, spaceBefore=0, spaceAfter=8))

    # Judul
    story.append(Paragraph("BERITA ACARA REKONSILIASI (BAR) BELANJA SEKOLAH", ParagraphStyle('T', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=11, alignment=1, spaceAfter=10)))
    
    style_body = ParagraphStyle('BodyTextCustom', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=13)

    pembuka_text = f"Pada Hari ini <b>{hari_str}</b> Tanggal <b>{tgl_str}</b> Bulan <b>{bln_str}</b> Tahun <b>{thn_str}</b>, kami yang bertanda tangan di bawah ini:"
    story.append(Paragraph(pembuka_text, style_body))
    story.append(Spacer(1, 6))

    # Biodata
    bio_table_data = [
        [Paragraph("1.", style_body), Paragraph("Nama", style_body), Paragraph(":", style_body), Paragraph(f"<b>{biodata_sekolah.get('nama', '-')}</b>", style_body)],
        [Paragraph("", style_body), Paragraph("NIP", style_body), Paragraph(":", style_body), Paragraph(biodata_sekolah.get('nip', '-'), style_body)],
        [Paragraph("", style_body), Paragraph("Pangkat / Gol. Ruang", style_body), Paragraph(":", style_body), Paragraph(biodata_sekolah.get('pangkat', '-'), style_body)],
        [Paragraph("", style_body), Paragraph("Jabatan", style_body), Paragraph(":", style_body), Paragraph(biodata_sekolah.get('jabatan', '-'), style_body)],
        [Paragraph("", style_body), Paragraph("Unit Kerja", style_body), Paragraph(":", style_body), Paragraph(biodata_sekolah.get('unit_kerja', sekolah_name), style_body)],
    ]
    
    t_bio = Table(bio_table_data, colWidths=[15, 120, 10, 405])
    t_bio.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
        ('TOPPADDING', (0,0), (-1,-1), 1),
    ]))
    story.append(t_bio)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Telah melakukan rekonsiliasi data pencatatan Belanja Sekolah antara Laporan Realisasi Belanja (SIPD) dengan Catatan BKU (ARKAS) dengan hasil rincian sebagai berikut:", style_body))
    story.append(Spacer(1, 8))

    # Tabel Rincian
    hdr_s = ParagraphStyle('TH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, alignment=1, textColor=colors.whitesmoke)
    table_data = [[
        Paragraph("No", hdr_s), Paragraph("Uraian Program / Kegiatan", hdr_s),
        Paragraph("Anggaran", hdr_s), Paragraph("Realisasi SIPD", hdr_s),
        Paragraph("Realisasi BKU", hdr_s), Paragraph("Sisa", hdr_s), Paragraph("Status", hdr_s)
    ]]

    b_s = ParagraphStyle('TB', parent=styles['Normal'], fontName='Helvetica', fontSize=7)
    b_c = ParagraphStyle('TBC', parent=styles['Normal'], fontName='Helvetica', fontSize=7, alignment=1)
    b_r = ParagraphStyle('TBR', parent=styles['Normal'], fontName='Helvetica', fontSize=7, alignment=2)
    
    tot_ang, tot_sipd, tot_bku, tot_sisa = 0.0, 0.0, 0.0, 0.0

    for idx, item in enumerate(detail_items, 1):
        ang = float(item.get('anggaran', 0.0))
        r_sipd = float(item.get('realisasi_sipd', 0.0))
        r_bku = float(item.get('realisasi_bku', 0.0))
        sisa = ang - r_sipd
        status = "Sesuai" if abs(r_sipd - r_bku) < 1 else "Tidak Sesuai"

        tot_ang += ang
        tot_sipd += r_sipd
        tot_bku += r_bku
        tot_sisa += sisa

        status_html = f"<font color='{'green' if status == 'Sesuai' else 'red'}'><b>{status}</b></font>"

        table_data.append([
            Paragraph(str(idx), b_c), Paragraph(str(item.get('uraian', '-')), b_s),
            Paragraph(f"Rp {ang:,.2f}", b_r), Paragraph(f"Rp {r_sipd:,.2f}", b_r),
            Paragraph(f"Rp {r_bku:,.2f}", b_r), Paragraph(f"Rp {sisa:,.2f}", b_r),
            Paragraph(status_html, b_c)
        ])

    tot_s = ParagraphStyle('TOT', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, alignment=2)
    table_data.append([
        Paragraph("<b>TOTAL</b>", ParagraphStyle('TOTT', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, alignment=1)),
        Paragraph("", tot_s), Paragraph(f"<b>Rp {tot_ang:,.2f}</b>", tot_s),
        Paragraph(f"<b>Rp {tot_sipd:,.2f}</b>", tot_s), Paragraph(f"<b>Rp {tot_bku:,.2f}</b>", tot_s),
        Paragraph(f"<b>Rp {tot_sisa:,.2f}</b>", tot_s), Paragraph("-", b_c)
    ])

    t = Table(table_data, colWidths=[20, 175, 70, 70, 70, 75, 70], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('SPAN', (0, -1), (1, -1)),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ecf0f1')),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    story.append(Paragraph(f"Demikian Berita Acara Rekonsiliasi Belanja {sekolah_name} ini dibuat dengan sebenarnya untuk dipergunakan sebagaimana mestinya.", style_body))
    story.append(Spacer(1, 15))

    # Tanda Tangan
    nama_p = biodata_sekolah.get('nama', '....................')
    nip_p = biodata_sekolah.get('nip', '....................')

    ttd_data = [
        [
            Paragraph(f"<b>Yang Menyerahkan:</b><br/>{biodata_sekolah.get('jabatan', 'Bendahara Sekolah')}", ParagraphStyle('TTDC', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=1)),
            Paragraph("<b>Yang Menerima:</b><br/>Tim Rekonsiliasi Dinas", ParagraphStyle('TTDC2', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=1))
        ],
        [Paragraph("<br/><br/><br/>", style_body), Paragraph("<br/><br/><br/>", style_body)],
        [
            Paragraph(f"<b><u>{nama_p}</u></b><br/>NIP. {nip_p}", ParagraphStyle('TTDN', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=1)),
            Paragraph("<b><u>Tim Verifikasi Dinas</u></b><br/>NIP. ....................", ParagraphStyle('TTDN2', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=1))
        ]
    ]
    t_ttd = Table(ttd_data, colWidths=[275, 275])
    t_ttd.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    story.append(t_ttd)

    doc.build(story)
    buffer.seek(0)
    return buffer

# --- STATE SESSION LOGIN ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_info' not in st.session_state:
    st.session_state['user_info'] = {}

# --- RUNNING TEXT DIBAGIAN ATAS ---
st.markdown("""
    <div class="running-text-box">
        <marquee behavior="scroll" direction="left" scrollamount="8" style="font-size: 30px; font-weight: bold; color: #15803d;">
            📢 Mari lakukan rekonsiliasi secara berkala dengan teliti dan disiplin. Data yang tertib menjadi dasar pelaporan yang akurat, tepat waktu, dan dapat dipertanggungjawabkan. Rekonsiliasi rutin, laporan semakin berkualitas!
        </marquee>
    </div>
""", unsafe_allow_html=True)

# --- AUTENTIKASI ---
st.sidebar.title("🔐 Keamanan Sistem")

if not st.session_state['logged_in']:
    st.sidebar.subheader("Silakan Login")
    username_input = st.sidebar.text_input("Username")
    password_input = st.sidebar.text_input("Password", type="password")
    
    if st.sidebar.button("Masuk"):
        clean_user = username_input.strip().lower()
        clean_pass = password_input.strip()
        
        if not clean_user or not clean_pass:
            st.sidebar.warning("Username dan Password tidak boleh kosong!")
        else:
            try:
                res = supabase.table("users").select("*").execute()
                all_users = res.data if res.data else []

                matched_user = next((u for u in all_users if str(u.get('username', '')).strip().lower() == clean_user), None)
                
                if matched_user:
                    stored_pass = str(matched_user.get('password', '')).strip()
                    if stored_pass == clean_pass:
                        st.session_state['logged_in'] = True
                        st.session_state['user_info'] = {
                            'username': matched_user['username'],
                            'nama_sekolah': matched_user['nama_sekolah'],
                            'role': matched_user['role']
                        }
                        st.rerun()
                    else:
                        st.sidebar.error("Password salah!")
                else:
                    st.sidebar.error("Username tidak ditemukan!")
            except Exception as e:
                st.sidebar.error(f"Koneksi Supabase gagal: {e}")

else:
    user = st.session_state['user_info']
    st.sidebar.success(f"Login sebagai:\n**{user['nama_sekolah']}**")
    st.sidebar.write(f"Role: `{user['role']}`")
    
    if st.sidebar.button("🚪 Logout / Keluar"):
        st.session_state['logged_in'] = False
        st.session_state['user_info'] = {}
        st.rerun()

# --- TAMPILAN UTAMA ---
st.title("📊 Aplikasi Rekonsiliasi Belanja Sekolah")
st.caption("Dinas Pendidikan dan Kebudayaan Kabupaten Buol")

if not st.session_state['logged_in']:
    st.info("Silakan login melalui menu di sebelah kiri untuk mengakses fitur sistem.")
else:
    user = st.session_state['user_info']
    st.divider()

    # ==========================================
    # ROLE: ADMIN DINAS
    # ==========================================
    if user['role'] == 'admin':
        st.subheader("👨‍💼 Panel Administrator Dinas Pendidikan")
        tab_admin_verifikasi, tab_admin_users, tab_admin_rekon = st.tabs([
            "🔍 Verifikasi Belanja Sekolah", 
            "👥 Manajemen Akun", 
            "📑 Rekapitulasi & BAR"
        ])

        # TAB 1: VERIFIKASI BELANJA
        with tab_admin_verifikasi:
            st.write("### 🔍 Panel Verifikasi Belanja Sekolah")
            try:
                res_pending = supabase.table("hasil_rekon").select("*").order("id", desc=True).execute()
                data_rekon = res_pending.data if res_pending.data else []
            except Exception as e:
                data_rekon = []
                st.error(f"Gagal mengambil data laporan: {e}")

            if data_rekon:
                df_p = pd.DataFrame(data_rekon)
                selected_sec = st.selectbox(
                    "Pilih Laporan Sekolah yang Ingin Diverifikasi:", 
                    options=df_p['id'].tolist(), 
                    format_func=lambda x: f"ID #{x} - {df_p[df_p['id']==x]['nama_sekolah'].values[0]} ({df_p[df_p['id']==x]['status'].values[0]})"
                )
                
                row_v = df_p[df_p['id'] == selected_sec].iloc[0]
                
                st.info(f"**Sekolah:** {row_v['nama_sekolah']} | **Tanggal Submit:** {row_v['tanggal_submit']} | **Status Saat Ini:** `{row_v['status']}`")

                bio_info = json.loads(row_v['biodata_json']) if row_v.get('biodata_json') else {}
                with st.expander("👤 Informasi Biodata Penandatangan/Pengirim Sekolah", expanded=True):
                    col_b1, col_b2 = st.columns(2)
                    col_b1.write(f"**Nama:** {bio_info.get('nama', row_v.get('nama_penandatangan', '-'))}")
                    col_b1.write(f"**NIP:** {bio_info.get('nip', row_v.get('nip_penandatangan', '-'))}")
                    col_b1.write(f"**Pangkat/Gol. Ruang:** {bio_info.get('pangkat', row_v.get('pangkat_penandatangan', '-'))}")
                    col_b2.write(f"**Jabatan:** {bio_info.get('jabatan', row_v.get('jabatan_penandatangan', '-'))}")
                    col_b2.write(f"**Unit Kerja:** {bio_info.get('unit_kerja', row_v.get('unit_kerja', row_v['nama_sekolah']))}")

                col1, col2, col3 = st.columns(3)
                col1.metric("Transaksi Cocok", f"{row_v['total_matched']}")
                col2.metric("Gantung SIPD", f"{row_v['total_only_sipd']}")
                col3.metric("Gantung BKU", f"{row_v['total_only_bank']}")

                st.write("#### 📋 Rincian Item Transaksi Belanja")
                detail_json = json.loads(row_v['detail_json']) if row_v.get('detail_json') else []
                if detail_json:
                    st.dataframe(pd.DataFrame(detail_json), use_container_width=True)

                st.markdown("---")
                st.write("#### ✍️ Form Keputusan Verifikasi Admin")
                
                with st.form(f"form_verifikasi_{row_v['id']}"):
                    new_status = st.selectbox("Keputusan Verifikasi:", ["Disetujui", "Ditolak / Perlu Perbaikan", "Menunggu Verifikasi"])
                    catatan = st.text_area("Catatan Admin / Alasan Penolakan (Optional):", value=row_v.get('catatan_admin', '') or '')
                    btn_v = st.form_submit_button("💾 Simpan Keputusan Verifikasi")

                    if btn_v:
                        try:
                            supabase.table("hasil_rekon").update({
                                'status': new_status,
                                'catatan_admin': catatan.strip()
                            }).eq("id", row_v['id']).execute()
                            st.success(f"Status laporan {row_v['nama_sekolah']} berhasil diperbarui menjadi: **{new_status}**")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Gagal memperbarui status: {e}")
            else:
                st.info("Belum ada data laporan yang dikirimkan oleh sekolah.")

        # TAB 2: MANAJEMEN AKUN
        with tab_admin_users:
            col_add, col_edit = st.columns(2)

            with col_add:
                st.write("### ➕ Tambah Akun Baru")
                with st.form("form_add_user"):
                    new_username = st.text_input("Username (Unik)")
                    new_password = st.text_input("Password", type="password")
                    new_nama_sekolah = st.text_input("Nama Instansi / Sekolah")
                    new_role = st.selectbox("Pilih Role / Hak Akses:", ["sekolah", "admin"])
                    submit_add = st.form_submit_button("➕ Simpan Akun Baru")

                    if submit_add:
                        if new_username and new_password and new_nama_sekolah:
                            clean_u = new_username.lower().strip()
                            try:
                                check_user = supabase.table("users").select("username").eq("username", clean_u).execute()
                                
                                if check_user.data and len(check_user.data) > 0:
                                    st.warning(f"⚠️ Username '{clean_u}' sudah terdaftar! Silakan gunakan username lain.")
                                else:
                                    supabase.table("users").insert({
                                        'username': clean_u,
                                        'password': new_password.strip(),
                                        'nama_sekolah': new_nama_sekolah.strip(),
                                        'role': new_role
                                    }).execute()
                                    st.success(f"✅ Akun **{new_role.upper()}** ({new_nama_sekolah}) berhasil dibuat!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Gagal menambah akun: {e}")
                        else:
                            st.warning("Mohon isi semua kolom form.")

            with col_edit:
                st.write("### ✏️ Kelola & Edit Akun Terdaftar")
                res_u = supabase.table("users").select("*").execute()
                all_u_data = res_u.data if res_u.data else []

                if all_u_data:
                    selected_user = st.selectbox(
                        "Pilih Akun yang Ingin Diubah:",
                        options=[u['username'] for u in all_u_data],
                        format_func=lambda x: f"{x} - {next((u['nama_sekolah'] for u in all_u_data if u['username'] == x), '')} ({next((u['role'] for u in all_u_data if u['username'] == x), '')})"
                    )

                    curr_user = next((u for u in all_u_data if u['username'] == selected_user), None)

                    if curr_user:
                        with st.form("form_edit_user"):
                            edit_nama_sekolah = st.text_input("Nama Instansi/Pengguna:", value=curr_user['nama_sekolah'])
                            edit_role = st.selectbox("Role / Hak Akses:", ["sekolah", "admin"], index=0 if curr_user['role'] == 'sekolah' else 1)
                            edit_password = st.text_input("Password Baru (Kosongkan jika tidak diubah):", type="password")
                            
                            submit_edit = st.form_submit_button("💾 Simpan Perubahan")

                            if submit_edit:
                                update_payload = {
                                    'nama_sekolah': edit_nama_sekolah.strip(),
                                    'role': edit_role
                                }
                                if edit_password.strip():
                                    update_payload['password'] = edit_password.strip()

                                try:
                                    supabase.table("users").update(update_payload).eq("username", selected_user).execute()
                                    supabase.table("hasil_rekon").update({'nama_sekolah': edit_nama_sekolah.strip()}).eq("username", selected_user).execute()
                                    st.success("Data akun berhasil diperbarui!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Gagal memperbarui: {e}")
                        
                        if st.button("🗑️ Hapus Akun Ini", type="secondary"):
                            try:
                                supabase.table("users").delete().eq("username", selected_user).execute()
                                st.success(f"Akun {selected_user} berhasil dihapus!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal menghapus akun: {e}")

        # TAB 3: REKAPITULASI & CETAK BAR
        with tab_admin_rekon:
            res_rekon = supabase.table("hasil_rekon").select("*").order("id", desc=True).execute()
            if res_rekon.data:
                df_rekon = pd.DataFrame(res_rekon.data)
                
                st.write("### 📈 Akumulasi Realisasi Seluruh Sekolah")
                df_disetujui = df_rekon[df_rekon['status'] == 'Disetujui']
                
                col_adm1, col_adm2, col_adm3 = st.columns(3)
                col_adm1.metric("Total Laporan Masuk", f"{len(df_rekon)} Laporan")
                col_adm2.metric("Laporan Disetujui", f"{len(df_disetujui)} Laporan")
                col_adm3.metric("Total Realisasi Disetujui", f"Rp {df_disetujui['nominal_cocok'].sum():,.2f}")

                st.divider()
                st.dataframe(df_rekon[['id', 'nama_sekolah', 'tanggal_submit', 'status', 'catatan_admin', 'total_matched', 'total_only_sipd', 'total_only_bank', 'nominal_cocok']], use_container_width=True)

                st.markdown("---")
                st.subheader("📄 Cetak Berita Acara Rekonsiliasi (BAR)")
                selected_id = st.selectbox("Pilih ID Laporan untuk Cetak PDF BAR:", df_rekon['id'].tolist())
                row_d = df_rekon[df_rekon['id'] == selected_id].iloc[0]

                st.write(f"**Sekolah:** {row_d['nama_sekolah']} | **Status Verifikasi:** `{row_d['status']}`")
                
                bio_info = json.loads(row_d['biodata_json']) if row_d.get('biodata_json') else {
                    'nama': row_d.get('nama_penandatangan', '-'),
                    'nip': row_d.get('nip_penandatangan', '-'),
                    'pangkat': row_d.get('pangkat_penandatangan', '-'),
                    'jabatan': row_d.get('jabatan_penandatangan', 'Bendahara Sekolah'),
                    'unit_kerja': row_d.get('unit_kerja', row_d['nama_sekolah'])
                }

                detail_items = json.loads(row_d['detail_json']) if row_d.get('detail_json') else []
                pdf_bar = generate_bar_pdf(row_d['nama_sekolah'], row_d['tanggal_submit'], detail_items, row_d['status'], bio_info)

                st.download_button(
                    label="🖨️ Unduh Berita Acara (PDF BAR)",
                    data=pdf_bar,
                    file_name=f"BAR_{row_d['nama_sekolah'].replace(' ', '_')}.pdf",
                    mime="application/pdf"
                )

    # ==========================================
    # ROLE: SEKOLAH / OPERATOR
    # ==========================================
    else:
        st.subheader(f"Input & Pengolahan Data: {user['nama_sekolah']}")
        tab_input, tab_history = st.tabs(["📥 Unggah Dokumen & Rekon", "📜 Riwayat Pengiriman & Verifikasi"])

        with tab_input:
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                pdf_sipd = st.file_uploader("Upload File Realisasi Belanja (SIPD)", type=["pdf"], key="sipd")
            with col_u2:
                pdf_bank = st.file_uploader("Upload File BKU (ARKAS)", type=["pdf"], key="bank")

            if pdf_sipd and pdf_bank:
                df_sipd = parse_pdf(pdf_sipd)
                df_bank = parse_pdf(pdf_bank)

                if not df_sipd.empty and not df_bank.empty:
                    auto_tgl_s, auto_nom_s, auto_ket_s, auto_ang_s = auto_detect_columns(df_sipd)
                    auto_tgl_b, auto_nom_b, auto_ket_b, _ = auto_detect_columns(df_bank)

                    if st.button("🚀 Jalankan Rekonsiliasi Otomatis", type="primary"):
                        def clean_amount(val):
                            if pd.isna(val): return 0.0
                            v = str(val).replace('.', '').replace(',', '.')
                            try: return float(v)
                            except: return 0.0

                        df_sipd['Nominal_Clean'] = df_sipd[auto_nom_s].apply(clean_amount)
                        df_sipd['Anggaran_Clean'] = df_sipd[auto_ang_s].apply(clean_amount) if auto_ang_s in df_sipd.columns else df_sipd['Nominal_Clean']
                        df_bank['Nominal_Clean'] = df_bank[auto_nom_b].apply(clean_amount)

                        merged = pd.merge(df_sipd, df_bank, left_on=[auto_tgl_s, 'Nominal_Clean'], right_on=[auto_tgl_b, 'Nominal_Clean'], how='outer', indicator=True)

                        matched = merged[merged['_merge'] == 'both']
                        only_sipd = merged[merged['_merge'] == 'left_only']
                        only_bank = merged[merged['_merge'] == 'right_only']

                        detail_items = []
                        for idx, row in df_sipd.iterrows():
                            real_sipd = float(row.get('Nominal_Clean', 0.0))
                            match_bku = df_bank[df_bank['Nominal_Clean'] == real_sipd]
                            detail_items.append({
                                'uraian': str(row.get(auto_ket_s, 'Kegiatan Belanja')),
                                'anggaran': float(row.get('Anggaran_Clean', 0.0)),
                                'realisasi_sipd': real_sipd,
                                'realisasi_bku': real_sipd if not match_bku.empty else 0.0
                            })

                        st.session_state['rekon_temp'] = {
                            'matched': len(matched),
                            'only_sipd': len(only_sipd),
                            'only_bank': len(only_bank),
                            'nom_cocok': matched['Nominal_Clean'].sum(),
                            'detail_items': detail_items
                        }

                        st.success("Pencocokan Otomatis Selesai!")
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Cocok", f"{len(matched)} Transaksi")
                        m2.metric("Gantung SIPD", f"{len(only_sipd)} Transaksi")
                        m3.metric("Gantung BKU", f"{len(only_bank)} Transaksi")

                    if 'rekon_temp' in st.session_state:
                        st.markdown("---")
                        st.write("### 📝 Lengkapi Biodata Pejabat / Penandatangan Sekolah")
                        st.caption("Data ini akan ditampilkan di Berita Acara Rekonsiliasi (BAR).")
                        
                        col_bio1, col_bio2 = st.columns(2)
                        with col_bio1:
                            input_nama = st.text_input("Nama Lengkap Pejabat/Bendahara:", placeholder="Contoh: Ahmad Yani, S.Pd.")
                            input_nip = st.text_input("NIP:", placeholder="Contoh: 19850101 201001 1 001")
                            input_pangkat = st.text_input("Pangkat / Gol. Ruang:", placeholder="Contoh: Penata / III/c")
                        with col_bio2:
                            input_jabatan = st.text_input("Jabatan:", value="Bendahara BOS", placeholder="Contoh: Bendahara BOS / Kepala Sekolah")
                            input_unit = st.text_input("Unit Kerja:", value=user['nama_sekolah'])

                        if st.button("📤 Kirim Hasil ke Admin Dinas", type="primary"):
                            if not input_nama.strip() or not input_nip.strip():
                                st.warning("⚠️ Mohon isi Nama dan NIP penandatangan terlebih dahulu.")
                            else:
                                res = st.session_state['rekon_temp']
                                biodata_payload = {
                                    'nama': input_nama.strip(),
                                    'nip': input_nip.strip(),
                                    'pangkat': input_pangkat.strip(),
                                    'jabatan': input_jabatan.strip(),
                                    'unit_kerja': input_unit.strip()
                                }

                                try:
                                    supabase.table("hasil_rekon").insert({
                                        'username': user['username'],
                                        'nama_sekolah': user['nama_sekolah'],
                                        'tanggal_submit': datetime.now().strftime("%Y-%m-%d %H:%M"),
                                        'total_matched': res['matched'],
                                        'total_only_sipd': res['only_sipd'],
                                        'total_only_bank': res['only_bank'],
                                        'nominal_cocok': float(res['nom_cocok']),
                                        'status': 'Menunggu Verifikasi',
                                        'catatan_admin': '',
                                        'detail_json': json.dumps(res['detail_items']),
                                        'biodata_json': json.dumps(biodata_payload)
                                    }).execute()

                                    st.balloons()
                                    st.success("Hasil rekonsiliasi berhasil terkirim ke Admin Dinas!")
                                    del st.session_state['rekon_temp']
                                except Exception as ex:
                                    st.error(f"Gagal menyimpan data: {ex}")

        # TAB RIWAYAT SEKOLAH SAFELY
        with tab_history:
            try:
                res_h = supabase.table("hasil_rekon")\
                    .select("*")\
                    .eq("username", user['username'])\
                    .order("id", desc=True)\
                    .execute()

                if res_h.data:
                    df_h = pd.DataFrame(res_h.data)

                    st.write("### 📊 Ringkasan Total Realisasi Bulanan")

                    total_akumulasi = df_h['nominal_cocok'].sum() if 'nominal_cocok' in df_h.columns else 0.0
                    jumlah_bulan = len(df_h)

                    c_rekap1, c_rekap2 = st.columns(2)
                    c_rekap1.metric("Total Pengiriman (Bulan/Laporan)", f"{jumlah_bulan} Kali")
                    c_rekap2.metric("Total Akumulasi Realisasi Cocok", f"Rp {total_akumulasi:,.2f}")

                    st.divider()
                    st.write("#### 📜 Detail Riwayat Pengiriman")
                    
                    show_cols = [c for c in ['tanggal_submit', 'status', 'nominal_cocok', 'total_matched', 'total_only_sipd', 'total_only_bank', 'catatan_admin'] if c in df_h.columns]
                    st.dataframe(df_h[show_cols], use_container_width=True)
                else:
                    st.info("Belum ada riwayat pengiriman.")
            except Exception as e:
                st.error(f"Gagal memuat riwayat pengiriman: {e}")

# --- FOOTER DI BAGIAN BAWAH HALAMAN ---
st.markdown("""
    <div class="footer-container">
        <div class="footer-spirit">🔥 Semangat Tim Verifikasi! 💪</div>
        <div class="footer-copyright">
            © 2026 Dinas Pendidikan dan Kebudayaan Kabupaten Buol. Hak Cipta Dilindungi Undang-Undang.
        </div>
    </div>
""", unsafe_allow_html=True)
