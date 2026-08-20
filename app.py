import streamlit as st
import pdfplumber
import pandas as pd
import io
import json
import hashlib
from datetime import datetime
from supabase import create_client, Client
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Konfigurasi Halaman Utama
st.set_page_config(page_title="Sistem Rekonsiliasi Belanja Sekolah - Kab. Buol", layout="wide")

# ==========================================
# KONFIGURASI SUPABASE (DATABASE & STORAGE PERMANEN)
# ==========================================
# Masukkan URL dan Key Supabase Anda di sini
SUPABASE_URL = "https://xxxxxxxxxxxx.supabase.co"
SUPABASE_KEY = "your-anon-key-here"

@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

# ==========================================
# HELPER FUNCTIONS & CETAK PDF BAR
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
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30)
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
        Paragraph("No", cell_hdr_style), Paragraph("Uraian Program / Kegiatan / Akun Belanja", cell_hdr_style),
        Paragraph("Jumlah Anggaran", cell_hdr_style), Paragraph("Realisasi SIPD", cell_hdr_style),
        Paragraph("Realisasi BKU (ARKAS)", cell_hdr_style), Paragraph("Sisa Anggaran", cell_hdr_style),
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
            Paragraph(str(idx), cell_body_center), Paragraph(str(item.get('uraian', '-')), cell_body_style),
            Paragraph(f"Rp {ang:,.2f}", cell_body_right), Paragraph(f"Rp {r_sipd:,.2f}", cell_body_right),
            Paragraph(f"Rp {r_bku:,.2f}", cell_body_right), Paragraph(f"Rp {sisa:,.2f}", cell_body_right),
            Paragraph(status_html, cell_body_center)
        ])

    cell_tot_style = ParagraphStyle('TOT', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=2)
    table_data.append([
        Paragraph("<b>TOTAL</b>", ParagraphStyle('TOTT', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, alignment=1)),
        Paragraph("", cell_tot_style), Paragraph(f"<b>Rp {tot_ang:,.2f}</b>", cell_tot_style),
        Paragraph(f"<b>Rp {tot_sipd:,.2f}</b>", cell_tot_style), Paragraph(f"<b>Rp {tot_bku:,.2f}</b>", cell_tot_style),
        Paragraph(f"<b>Rp {tot_sisa:,.2f}</b>", cell_tot_style), Paragraph("-", cell_body_center)
    ])

    t = Table(table_data, colWidths=[20, 175, 70, 70, 70, 75, 70], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4), ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey), ('SPAN', (0, -1), (1, -1)),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ecf0f1')),
    ]))
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
# AUTENTIKASI AKUN
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
        res = supabase.table("users").select("*").eq("username", username_input.lower().strip()).execute()
        users = res.data
        
        if users and (users[0]['password'] == password_input or check_hashes(password_input, users[0]['password'])):
            st.session_state['logged_in'] = True
            st.session_state['user_info'] = {
                'username': users[0]['username'],
                'nama_sekolah': users[0]['nama_sekolah'],
                'role': users[0]['role']
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
    st.caption("Dinas Pendidikan dan Kebudayaan Kabupaten Buol")

    # ==========================================
    # HALAMAN SEKOLAH
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

                    if st.button("🚀 Jalankan Rekonsiliasi Otomatis", type="primary"):
                        def clean_amount(val):
                            if pd.isna(val): return 0.0
                            val_str = str(val).replace('.', '').replace(',', '.')
                            try: return float(val_str)
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
                            'detail_items': detail_items,
                            'bytes_sipd': pdf_sipd.getvalue(),
                            'bytes_bank': pdf_bank.getvalue(),
                            'filename_sipd': pdf_sipd.name,
                            'filename_bank': pdf_bank.name
                        }

                        st.success("Pencocokan Otomatis Selesai!")
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Cocok", f"{len(matched)} Transaksi")
                        m2.metric("Gantung SIPD", f"{len(only_sipd)} Transaksi")
                        m3.metric("Gantung BKU", f"{len(only_bank)} Transaksi")

                    if 'rekon_temp' in st.session_state:
                        if st.button("📤 Kirim Hasil & File ke Admin Dinas"):
                            res = st.session_state['rekon_temp']
                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                            
                            # Upload File PDF ke Storage Supabase Permanen
                            path_sipd = f"{user_data['username']}/{timestamp}_SIPD.pdf"
                            path_bank = f"{user_data['username']}/{timestamp}_BKU.pdf"

                            supabase.storage.from_("dokumen-rekon").upload(path_sipd, res['bytes_sipd'])
                            supabase.storage.from_("dokumen-rekon").upload(path_bank, res['bytes_bank'])

                            url_sipd = supabase.storage.from_("dokumen-rekon").get_public_url(path_sipd)
                            url_bank = supabase.storage.from_("dokumen-rekon").get_public_url(path_bank)

                            # Simpan ke Database Cloud
                            supabase.table("hasil_rekon").insert({
                                'username': user_data['username'],
                                'nama_sekolah': user_data['nama_sekolah'],
                                'tanggal_submit': datetime.now().strftime("%Y-%m-%d %H:%M"),
                                'total_matched': res['matched'],
                                'total_only_sipd': res['only_sipd'],
                                'total_only_bank': res['only_bank'],
                                'nominal_cocok': res['nom_cocok'],
                                'status': 'Terkirim',
                                'detail_json': json.dumps(res['detail_items']),
                                'file_sipd_url': url_sipd,
                                'file_bank_url': url_bank
                            }).execute()

                            st.balloons()
                            st.success("Hasil & Dokumen PDF Berhasil Tersimpan Permanen!")
                            del st.session_state['rekon_temp']

        with tab_history:
            res = supabase.table("hasil_rekon").select("tanggal_submit, total_matched, total_only_sipd, total_only_bank, nominal_cocok, status").eq("username", user_data['username']).order("id", desc=True).execute()
            st.dataframe(pd.DataFrame(res.data), use_container_width=True)

    # ==========================================
    # HALAMAN ADMIN DINAS
    # ==========================================
    elif user_data['role'] == 'admin':
        st.subheader("👨‍💼 Panel Administrator Dinas Pendidikan")
        
        res = supabase.table("hasil_rekon").select("*").order("id", desc=True).execute()
        df_db = pd.DataFrame(res.data)

        if df_db.empty:
            st.info("Belum ada laporan rekonsiliasi yang terkirim.")
        else:
            st.dataframe(df_db[['id', 'nama_sekolah', 'tanggal_submit', 'total_matched', 'total_only_sipd', 'total_only_bank', 'nominal_cocok', 'status']], use_container_width=True)

            selected_id = st.selectbox("Pilih ID Pengajuan:", df_db['id'].tolist())
            row_data = df_db[df_db['id'] == selected_id].iloc[0]

            st.markdown(f"**Lampiran File:** [📄 PDF SIPD]({row_data['file_sipd_url']}) | [📄 PDF BKU]({row_data['file_bank_url']})")

            detail_items = json.loads(row_data['detail_json']) if row_data['detail_json'] else []
            pdf_bar = generate_bar_pdf(row_data['nama_sekolah'], row_data['tanggal_submit'], detail_items)

            st.download_button(
                label="🖨️ Download Berita Acara Rincian Belanja (PDF)",
                data=pdf_bar,
                file_name=f"BAR_Rincian_{row_data['nama_sekolah'].replace(' ', '_')}.pdf",
                mime="application/pdf"
            )
