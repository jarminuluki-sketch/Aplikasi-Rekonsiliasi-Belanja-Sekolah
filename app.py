import streamlit as st
import pdfplumber
import pandas as pd
import sqlite3
import io
import json
import hashlib
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Konfigurasi Halaman Utama
st.set_page_config(page_title="Sistem Rekonsiliasi Belanja Sekolah - Kab. Buol", layout="wide")

# Helper Hash Password
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

# ==========================================
# 1. INISIALISASI DATABASE SQLITE
# ==========================================
def init_db():
    conn = sqlite3.connect("rekonsiliasi.db")
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            nama_sekolah TEXT,
            role TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS hasil_rekon (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            nama_sekolah TEXT,
            tanggal_submit TEXT,
            total_matched INTEGER,
            total_only_sipd INTEGER,
            total_only_bank INTEGER,
            nominal_cocok REAL,
            status TEXT,
            detail_json TEXT
        )
    ''')
    
    # Penambahan Kolom Otomatis jika belum ada
    columns_users = [row[1] for row in c.execute("PRAGMA table_info(users)").fetchall()]
    if 'nama_sekolah' not in columns_users:
        c.execute("ALTER TABLE users ADD COLUMN nama_sekolah TEXT")
    
    columns_rekon = [row[1] for row in c.execute("PRAGMA table_info(hasil_rekon)").fetchall()]
    if 'username' not in columns_rekon:
        c.execute("ALTER TABLE hasil_rekon ADD COLUMN username TEXT")
    if 'nama_sekolah' not in columns_rekon:
        c.execute("ALTER TABLE hasil_rekon ADD COLUMN nama_sekolah TEXT")
    if 'detail_json' not in columns_rekon:
        c.execute("ALTER TABLE hasil_rekon ADD COLUMN detail_json TEXT")

    # Akun Default
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (username, password, nama_sekolah, role) VALUES (?, ?, ?, ?)",
                  ('admin', make_hashes('admin123'), 'Admin Dinas Pendidikan', 'admin'))
        c.execute("INSERT INTO users (username, password, nama_sekolah, role) VALUES (?, ?, ?, ?)",
                  ('smp2karamat', make_hashes('smp123'), 'SMP Negeri 2 Karamat', 'sekolah'))
    
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 2. HELPER FUNCTIONS & CETAK PDF BAR
# ==========================================
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
    df = df[df[df.columns[0]] != df.columns[0]]
    return df

def auto_detect_columns(df):
    tgl_col, nom_col, ket_col, ang_col = None, None, None, None
    for col in df.columns:
        col_lower = str(col).lower()
        if not tgl_col and any(k in col_lower for k in ['tgl', 'tanggal', 'date']):
            tgl_col = col
        elif not nom_col and any(k in col_lower for k in ['realisasi', 'nominal', 'jumlah', 'nilai', 'pengeluaran']):
            nom_col = col
        elif not ket_col and any(k in col_lower for k in ['uraian', 'keterangan', 'deskripsi', 'nama akun', 'kegiatan', 'program']):
            ket_col = col
        elif not ang_col and any(k in col_lower for k in ['anggaran', 'pagu', 'alokasi']):
            ang_col = col

    cols = list(df.columns)
    if not tgl_col and len(cols) > 0: tgl_col = cols[0]
    if not nom_col and len(cols) > 1: nom_col = cols[1]
    if not ket_col and len(cols) > 2: ket_col = cols[2]
    if not ang_col and len(cols) > 3: ang_col = cols[3]
    
    return tgl_col, nom_col, ket_col, ang_col

def generate_bar_pdf(sekolah_name, tanggal_submit, detail_items):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter,
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30
    )
    styles = getSampleStyleSheet()
    story = []

    kop_header_style = ParagraphStyle('KopHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=13, leading=15, alignment=1)
    kop_sub_style = ParagraphStyle('KopSub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=14, leading=16, alignment=1)
    kop_alamat_style = ParagraphStyle('KopAlamat', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, alignment=1)

    story.append(Paragraph("PEMERINTAH KABUPATEN BUOL", kop_header_style))
    story.append(Paragraph("DINAS PENDIDIKAN DAN KEBUDAYAAN", kop_sub_style))
    story.append(Paragraph("Alamat : Jl. Batalipu Kel. Leok II Kecamatan Biau - Kode Pos : 94563", kop_alamat_style))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.black, spaceBefore=0, spaceAfter=10))

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=11, alignment=1, spaceAfter=10)
    story.append(Paragraph("BERITA ACARA REKONSILIASI (BAR) BELANJA SEKOLAH", title_style))
    
    style_meta = ParagraphStyle('MetaText', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=12)
    story.append(Paragraph(f"<b>Nama Sekolah:</b> {sekolah_name}", style_meta))
    story.append(Paragraph(f"<b>Tanggal Rekonsiliasi:</b> {tanggal_submit}", style_meta))
    story.append(Spacer(1, 8))

    ptext = "Pada hari ini telah dilakukan rekonsiliasi data pencatatan Belanja Sekolah antara Laporan Realisasi Belanja (SIPD) dengan Catatan BKU (ARKAS) dengan hasil rincian sebagai berikut:"
    story.append(Paragraph(ptext, style_meta))
    story.append(Spacer(1, 10))

    cell_hdr_style = ParagraphStyle('TH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=1, textColor=colors.whitesmoke)
    
    table_data = [[
        Paragraph("No", cell_hdr_style),
        Paragraph("Uraian Program / Kegiatan / Akun Belanja", cell_hdr_style),
        Paragraph("Jumlah Anggaran", cell_hdr_style),
        Paragraph("Realisasi SIPD", cell_hdr_style),
        Paragraph("Realisasi BKU (ARKAS)", cell_hdr_style),
        Paragraph("Sisa Anggaran", cell_hdr_style),
        Paragraph("Keterangan", cell_hdr_style)
    ]]

    cell_body_style = ParagraphStyle('TB', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=9)
    cell_body_center = ParagraphStyle('TBC', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=9, alignment=1)
    cell_body_right = ParagraphStyle('TBR', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=9, alignment=2)
    
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

        status_color = "green" if status == "Sesuai" else "red"
        status_html = f"<font color='{status_color}'><b>{status}</b></font>"

        table_data.append([
            Paragraph(str(idx), cell_body_center),
            Paragraph(str(item.get('uraian', '-')), cell_body_style),
            Paragraph(f"Rp {ang:,.2f}", cell_body_right),
            Paragraph(f"Rp {r_sipd:,.2f}", cell_body_right),
            Paragraph(f"Rp {r_bku:,.2f}", cell_body_right),
            Paragraph(f"Rp {sisa:,.2f}", cell_body_right),
            Paragraph(status_html, cell_body_center)
        ])

    cell_tot_style = ParagraphStyle('TOT', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=2)
    table_data.append([
        Paragraph("<b>TOTAL</b>", ParagraphStyle('TOTT', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, alignment=1)),
        Paragraph("", cell_tot_style),
        Paragraph(f"<b>Rp {tot_ang:,.2f}</b>", cell_tot_style),
        Paragraph(f"<b>Rp {tot_sipd:,.2f}</b>", cell_tot_style),
        Paragraph(f"<b>Rp {tot_bku:,.2f}</b>", cell_tot_style),
        Paragraph(f"<b>Rp {tot_sisa:,.2f}</b>", cell_tot_style),
        Paragraph("-", cell_body_center)
    ])

    col_widths = [20, 175, 70, 70, 70, 75, 70]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    t_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('SPAN', (0, -1), (1, -1)),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ecf0f1')),
    ]
    t.setStyle(TableStyle(t_style))
    story.append(t)
    story.append(Spacer(1, 15))

    penutup_text = f"Demikian Berita Acara Rekonsiliasi Belanja {sekolah_name} ini dibuat dan dilaksanakan untuk dipergunakan sebagaimana mestinya."
    story.append(Paragraph(penutup_text, style_meta))
    story.append(Spacer(1, 25))

    ttd_data = [
        ["Bendahara / Operator Sekolah", "Tim Rekonsiliasi Dinas"],
        ["\n\n\n__________________", "\n\n\n__________________"]
    ]
    t_ttd = Table(ttd_data, colWidths=[275, 275])
    t_ttd.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    story.append(t_ttd)

    doc.build(story)
    buffer.seek(0)
    return buffer

# ==========================================
# 3. AUTENTIKASI AKUN
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_info' not in st.session_state:
    st.session_state['user_info'] = None

st.sidebar.title("🔐 Keamanan Sistem")

if not st.session_state['logged_in']:
    st.sidebar.subheader("Silakan Login Sekolah")
    username_input = st.sidebar.text_input("Username")
    password_input = st.sidebar.text_input("Password", type="password")
    
    if st.sidebar.button("Masuk"):
        conn = sqlite3.connect("rekonsiliasi.db")
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username_input.lower().strip(),))
        user = c.fetchone()
        conn.close()
        
        if user and check_hashes(password_input, user[2]):
            st.session_state['logged_in'] = True
            st.session_state['user_info'] = {
                'username': user[1],
                'nama_sekolah': user[3] if len(user) > 3 and user[3] else user[1],
                'role': user[4] if len(user) > 4 else 'sekolah'
            }
            st.rerun()
        else:
            st.sidebar.error("Username atau Password salah!")

    st.title("📊 Aplikasi Rekonsiliasi Belanja Sekolah")
    st.subheader("Dinas Pendidikan dan Kebudayaan Kabupaten Buol")
    st.info("Silakan login melalui menu di sebelah kiri untuk mengakses fitur sistem.")

else:
    user_data = st.session_state['user_info']
    st.sidebar.success(f"Login sebagai:\n**{user_data['nama_sekolah']}**")
    
    if st.sidebar.button("🚪 Logout / Keluar"):
        st.session_state['logged_in'] = False
        st.session_state['user_info'] = None
        st.rerun()

    st.title("📊 Aplikasi Rekonsiliasi Belanja Sekolah")
    st.caption("Dinas Pendidikan dan Kebudayaan Kabupaten Buol (TK, SD, dan SMP)")

    # ==========================================
    # 4. HALAMAN SEKOLAH
    # ==========================================
    if user_data['role'] == 'sekolah':
        st.subheader(f"Input & Pengolahan Data: {user_data['nama_sekolah']}")
        
        tab_input, tab_history = st.tabs(["📥 Unggah Dokumen & Rekon", "📜 Riwayat Pengiriman"])

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

                    with st.expander("🛠️ Pengaturan Pemetaan Kolom (Otomatis)", expanded=False):
                        c1, c2, c3, c4 = st.columns(4)
                        with c1:
                            col_tgl_s = st.selectbox("Tgl SIPD", df_sipd.columns, index=list(df_sipd.columns).index(auto_tgl_s))
                            col_tgl_b = st.selectbox("Tgl BKU", df_bank.columns, index=list(df_bank.columns).index(auto_tgl_b))
                        with c2:
                            col_nom_s = st.selectbox("Realisasi SIPD", df_sipd.columns, index=list(df_sipd.columns).index(auto_nom_s))
                            col_nom_b = st.selectbox("Realisasi BKU", df_bank.columns, index=list(df_bank.columns).index(auto_nom_b))
                        with c3:
                            col_ket_s = st.selectbox("Uraian SIPD", df_sipd.columns, index=list(df_sipd.columns).index(auto_ket_s))
                            col_ket_b = st.selectbox("Uraian BKU", df_bank.columns, index=list(df_bank.columns).index(auto_ket_b))
                        with c4:
                            col_ang_s = st.selectbox("Anggaran SIPD", df_sipd.columns, index=list(df_sipd.columns).index(auto_ang_s))

                    st.markdown("---")
                    if st.button("🚀 Jalankan Rekonsiliasi Otomatis", type="primary"):
                        def clean_amount(val):
                            if pd.isna(val): return 0.0
                            val_str = str(val).replace('.', '').replace(',', '.')
                            try: return float(val_str)
                            except: return 0.0

                        df_sipd['Nominal_Clean'] = df_sipd[col_nom_s].apply(clean_amount)
                        df_sipd['Anggaran_Clean'] = df_sipd[col_ang_s].apply(clean_amount) if col_ang_s in df_sipd.columns else df_sipd['Nominal_Clean']
                        df_bank['Nominal_Clean'] = df_bank[col_nom_b].apply(clean_amount)

                        merged = pd.merge(
                            df_sipd, df_bank,
                            left_on=[col_tgl_s, 'Nominal_Clean'],
                            right_on=[col_tgl_b, 'Nominal_Clean'],
                            how='outer', indicator=True
                        )

                        matched = merged[merged['_merge'] == 'both']
                        only_sipd = merged[merged['_merge'] == 'left_only']
                        only_bank = merged[merged['_merge'] == 'right_only']
                        total_nom_cocok = matched['Nominal_Clean'].sum()

                        detail_items = []
                        for idx, row in df_sipd.iterrows():
                            uraian_txt = str(row.get(col_ket_s, 'Kegiatan Belanja'))
                            ang_val = float(row.get('Anggaran_Clean', 0.0))
                            real_sipd = float(row.get('Nominal_Clean', 0.0))
                            
                            match_bku = df_bank[df_bank['Nominal_Clean'] == real_sipd]
                            real_bku = real_sipd if not match_bku.empty else 0.0

                            detail_items.append({
                                'uraian': uraian_txt,
                                'anggaran': ang_val,
                                'realisasi_sipd': real_sipd,
                                'realisasi_bku': real_bku
                            })

                        st.session_state['rekon_temp'] = {
                            'matched': len(matched),
                            'only_sipd': len(only_sipd),
                            'only_bank': len(only_bank),
                            'nom_cocok': total_nom_cocok,
                            'detail_items': detail_items
                        }

                        st.success("Pencocokan Otomatis Selesai!")
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Cocok", f"{len(matched)} Transaksi")
                        m2.metric("Gantung Realisasi SIPD", f"{len(only_sipd)} Transaksi")
                        m3.metric("Gantung BKU ARKAS", f"{len(only_bank)} Transaksi")

                    if 'rekon_temp' in st.session_state:
                        if st.button("📤 Kirim Hasil ke Admin Dinas"):
                            res = st.session_state['rekon_temp']
                            detail_json_str = json.dumps(res['detail_items'])
                            
                            conn = sqlite3.connect("rekonsiliasi.db")
                            c = conn.cursor()
                            c.execute('''
                                INSERT INTO hasil_rekon (username, nama_sekolah, tanggal_submit, total_matched, total_only_sipd, total_only_bank, nominal_cocok, status, detail_json)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (user_data['username'], user_data['nama_sekolah'], datetime.now().strftime("%Y-%m-%d %H:%M"), 
                                  res['matched'], res['only_sipd'], res['only_bank'], res['nom_cocok'], "Terkirim", detail_json_str))
                            conn.commit()
                            conn.close()
                            st.balloons()
                            st.success("Hasil rekonsiliasi rincian anggaran berhasil terkirim ke Admin Dinas!")
                            del st.session_state['rekon_temp']

        with tab_history:
            conn = sqlite3.connect("rekonsiliasi.db")
            df_my = pd.read_sql_query("SELECT tanggal_submit, total_matched, total_only_sipd, total_only_bank, nominal_cocok, status FROM hasil_rekon WHERE username = ? ORDER BY id DESC", conn, params=(user_data['username'],))
            conn.close()
            st.write("Riwayat Pengajuan Rekonsiliasi Sekolah Anda:")
            st.dataframe(df_my, use_container_width=True)

    # ==========================================
    # 5. HALAMAN ADMIN DINAS
    # ==========================================
    elif user_data['role'] == 'admin':
        st.subheader("👨‍💼 Panel Administrator Dinas Pendidikan dan Kebudayaan")
        
        tab_admin_rekon, tab_admin_users = st.tabs(["📑 Rekapitulasi & Cetak BAR", "🏫 Manajemen Akun Sekolah"])

        with tab_admin_rekon:
            conn = sqlite3.connect("rekonsiliasi.db")
            df_db = pd.read_sql_query("SELECT id, username, nama_sekolah, tanggal_submit, total_matched, total_only_sipd, total_only_bank, nominal_cocok, status, detail_json FROM hasil_rekon ORDER BY id DESC", conn)
            conn.close()

            if df_db.empty:
                st.info("Belum ada Sekolah yang mengirimkan laporan rekonsiliasi.")
            else:
                st.write("Daftar Laporan Rekonsiliasi Masuk dari Sekolah:")
                st.dataframe(df_db[['id', 'nama_sekolah', 'tanggal_submit', 'total_matched', 'total_only_sipd', 'total_only_bank', 'nominal_cocok', 'status']], use_container_width=True)

                st.markdown("---")
                st.subheader("📄 Cetak Berita Acara Rekonsiliasi (BAR) Rincian Belanja")
                selected_id = st.selectbox("Pilih ID Pengajuan:", df_db['id'].tolist())
                row_data = df_db[df_db['id'] == selected_id].iloc[0]

                st.write(f"**Nama Sekolah:** {row_data['nama_sekolah']}")
                st.write(f"**Waktu Kirim:** {row_data['tanggal_submit']}")
                
                try:
                    detail_items = json.loads(row_data['detail_json']) if row_data['detail_json'] else []
                except:
                    detail_items = []

                pdf_bar = generate_bar_pdf(
                    row_data['nama_sekolah'],
                    row_data['tanggal_submit'],
                    detail_items
                )

                st.download_button(
                    label="🖨️ Download Berita Acara Rincian Belanja (PDF)",
                    data=pdf_bar,
                    file_name=f"BAR_Rincian_{row_data['nama_sekolah'].replace(' ', '_')}.pdf",
                    mime="application/pdf"
                )

        with tab_admin_users:
            col_left, col_right = st.columns(2)

            with col_left:
                st.subheader("➕ Tambah Akun Sekolah Baru")
                with st.form("form_add_user"):
                    new_username = st.text_input("Username Sekolah (Misal: smpn2karamat)")
                    new_password = st.text_input("Password", type="password")
                    new_nama_sekolah = st.text_input("Nama Resmi Sekolah (Misal: SMP Negeri 2 Karamat)")
                    submit_user = st.form_submit_button("Simpan Akun Sekolah")

                    if submit_user:
                        if new_username and new_password and new_nama_sekolah:
                            try:
                                conn = sqlite3.connect("rekonsiliasi.db")
                                c = conn.cursor()
                                c.execute("INSERT INTO users (username, password, nama_sekolah, role) VALUES (?, ?, ?, ?)",
                                          (new_username.lower().strip(), make_hashes(new_password), new_nama_sekolah, 'sekolah'))
                                conn.commit()
                                conn.close()
                                st.success(f"Akun untuk **{new_nama_sekolah}** berhasil ditambahkan!")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Username sudah terpakai! Gunakan username lain.")
                        else:
                            st.warning("Mohon lengkapi seluruh kolom formulir.")

            with col_right:
                st.subheader("✏️ Edit Nama Sekolah & Password")
                conn = sqlite3.connect("rekonsiliasi.db")
                df_sekolah = pd.read_sql_query("SELECT username, nama_sekolah FROM users WHERE role = 'sekolah'", conn)
                conn.close()

                if not df_sekolah.empty:
                    selected_user = st.selectbox("Pilih Sekolah yang Ingin Diubah:", df_sekolah['username'].tolist())
                    user_curr_name = df_sekolah[df_sekolah['username'] == selected_user]['nama_sekolah'].values[0]

                    with st.form("form_edit_user"):
                        updated_nama_sekolah = st.text_input("Nama Sekolah Baru:", value=user_curr_name)
                        updated_password = st.text_input("Password Baru (Kosongkan jika tidak diubah):", type="password")
                        submit_edit = st.form_submit_button("Simpan Perubahan")

                        if submit_edit:
                            conn = sqlite3.connect("rekonsiliasi.db")
                            c = conn.cursor()
                            
                            c.execute("UPDATE users SET nama_sekolah = ? WHERE username = ?", (updated_nama_sekolah, selected_user))
                            c.execute("UPDATE hasil_rekon SET nama_sekolah = ? WHERE username = ?", (updated_nama_sekolah, selected_user))

                            if updated_password:
                                c.execute("UPDATE users SET password = ? WHERE username = ?", (make_hashes(updated_password), selected_user))

                            conn.commit()
                            conn.close()
                            st.success("Data Sekolah berhasil diperbarui!")
                            st.rerun()
                else:
                    st.info("Belum ada akun Sekolah yang terdaftar.")

            st.markdown("---")
            st.subheader("📋 Daftar Akun Sekolah Terdaftar")
            conn = sqlite3.connect("rekonsiliasi.db")
            df_users = pd.read_sql_query("SELECT id, username, nama_sekolah, role FROM users", conn)
            conn.close()
            st.dataframe(df_users, use_container_width=True)
