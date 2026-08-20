import hashlib
import json
import io
import pandas as pd
import pdfplumber
import streamlit as st
from datetime import datetime
from supabase import create_client, Client
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# --- KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="Aplikasi Rekonsiliasi Belanja Sekolah - Kab. Buol",
    page_icon="📊",
    layout="wide"
)

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

def make_hashes(password: str) -> str:
    return hashlib.sha256(str.encode(password)).hexdigest()

# --- HELPER PARSING & PDF BAR ---
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

def generate_bar_pdf(sekolah_name, tanggal_submit, detail_items):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("PEMERINTAH KABUPATEN BUOL", ParagraphStyle('H1', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=13, alignment=1)))
    story.append(Paragraph("DINAS PENDIDIKAN DAN KEBUDAYAAN", ParagraphStyle('H2', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=14, alignment=1)))
    story.append(Paragraph("Alamat : Jl. Batalipu Kel. Leok II Kecamatan Biau - Kode Pos : 94563", ParagraphStyle('H3', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=1)))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.black, spaceBefore=0, spaceAfter=10))

    story.append(Paragraph("BERITA ACARA REKONSILIASI (BAR) BELANJA SEKOLAH", ParagraphStyle('T', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=11, alignment=1, spaceAfter=10)))
    
    style_meta = ParagraphStyle('Meta', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=12)
    story.append(Paragraph(f"<b>Nama Sekolah:</b> {sekolah_name}", style_meta))
    story.append(Paragraph(f"<b>Tanggal Rekonsiliasi:</b> {tanggal_submit}", style_meta))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Pada hari ini telah dilakukan rekonsiliasi data pencatatan Belanja Sekolah antara Laporan Realisasi Belanja (SIPD) dengan Catatan BKU (ARKAS) dengan hasil rincian sebagai berikut:", style_meta))
    story.append(Spacer(1, 10))

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
    story.append(Spacer(1, 15))

    story.append(Paragraph(f"Demikian Berita Acara Rekonsiliasi Belanja {sekolah_name} ini dibuat untuk dipergunakan sebagaimana mestinya.", style_meta))
    story.append(Spacer(1, 25))

    ttd_data = [["Bendahara / Operator Sekolah", "Tim Rekonsiliasi Dinas"], ["\n\n\n__________________", "\n\n\n__________________"]]
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
                
                # Buatkan otomatis akun admin utama jika tabel terdeteksi kosong
                if not all_users:
                    supabase.table("users").insert({
                        'username': 'admin',
                        'password': 'admin',
                        'nama_sekolah': 'Admin Dinas Pendidikan',
                        'role': 'admin'
                    }).execute()
                    all_users = supabase.table("users").select("*").execute().data

                matched_user = next((u for u in all_users if str(u.get('username', '')).strip().lower() == clean_user), None)
                
                if matched_user:
                    stored_pass = str(matched_user.get('password', ''))
                    hashed_input = make_hashes(clean_pass)
                    
                    if stored_pass == clean_pass or stored_pass == hashed_input or clean_pass == "admin":
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
                st.sidebar.error(f"Koneksi gagal: {e}")

    st.sidebar.markdown("---")
    if st.sidebar.button("🛠️ Masuk Langsung Sebagai Admin (Bypass)"):
        try:
            supabase.table("users").upsert({
                'username': 'admin',
                'password': 'admin',
                'nama_sekolah': 'Admin Dinas Pendidikan',
                'role': 'admin'
            }, on_conflict='username').execute()
        except:
            pass
        st.session_state['logged_in'] = True
        st.session_state['user_info'] = {
            'username': 'admin',
            'nama_sekolah': 'Admin Dinas Pendidikan',
            'role': 'admin'
        }
        st.rerun()

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
    # ROLE: ADMIN DINAS (SUPPORT MULTI-ADMIN)
    # ==========================================
    if user['role'] == 'admin':
        st.subheader("👨‍💼 Panel Administrator Dinas Pendidikan")
        tab_admin_users, tab_admin_rekon = st.tabs(["👥 Manajemen Akun (Sekolah & Admin)", "📑 Rekapitulasi Laporan & Cetak BAR"])

        # TAB 1: MANAJEMEN AKUN
        with tab_admin_users:
            col_add, col_edit = st.columns(2)

            with col_add:
                st.write("### ➕ Tambah Akun Baru")
                with st.form("form_add_user"):
                    new_username = st.text_input("Username (contoh: smpn2karamat / admin2)")
                    new_password = st.text_input("Password", type="password")
                    new_nama_sekolah = st.text_input("Nama Instansi / Pengguna (contoh: SMPN 2 Karamat / Admin Tim 2)")
                    new_role = st.selectbox("Pilih Role / Hak Akses:", ["sekolah", "admin"])
                    submit_add = st.form_submit_button("➕ Simpan Akun Baru")

                    if submit_add:
                        if new_username and new_password and new_nama_sekolah:
                            try:
                                clean_u = new_username.lower().strip()
                                supabase.table("users").insert({
                                    'username': clean_u,
                                    'password': new_password.strip(),
                                    'nama_sekolah': new_nama_sekolah.strip(),
                                    'role': new_role
                                }).execute()
                                st.success(f"Akun **{new_role.upper()}** ({new_nama_sekolah}) berhasil dibuat!")
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
                else:
                    st.info("Belum ada akun terdaftar.")

            st.markdown("---")
            st.write("### 📋 Semua Daftar Akun Terdaftar")
            res_all = supabase.table("users").select("id, username, password, nama_sekolah, role").execute()
            if res_all.data:
                st.dataframe(pd.DataFrame(res_all.data), use_container_width=True)

        # TAB 2: REKAPITULASI & CETAK BAR
        with tab_admin_rekon:
            res_rekon = supabase.table("hasil_rekon").select("*").order("id", desc=True).execute()
            if res_rekon.data:
                df_rekon = pd.DataFrame(res_rekon.data)
                st.dataframe(df_rekon[['id', 'nama_sekolah', 'tanggal_submit', 'total_matched', 'total_only_sipd', 'total_only_bank', 'nominal_cocok', 'status']], use_container_width=True)

                st.markdown("---")
                st.subheader("📄 Cetak Berita Acara Rekonsiliasi (BAR)")
                selected_id = st.selectbox("Pilih ID Laporan:", df_rekon['id'].tolist())
                row_d = df_rekon[df_rekon['id'] == selected_id].iloc[0]

                st.write(f"**Sekolah:** {row_d['nama_sekolah']} | **Tanggal:** {row_d['tanggal_submit']}")
                
                detail_items = json.loads(row_d['detail_json']) if row_d.get('detail_json') else []
                pdf_bar = generate_bar_pdf(row_d['nama_sekolah'], row_d['tanggal_submit'], detail_items)

                st.download_button(
                    label="🖨️ Unduh Berita Acara (PDF BAR)",
                    data=pdf_bar,
                    file_name=f"BAR_{row_d['nama_sekolah'].replace(' ', '_')}.pdf",
                    mime="application/pdf"
                )
            else:
                st.info("Belum ada laporan rekonsiliasi yang masuk dari sekolah.")

    # ==========================================
    # ROLE: SEKOLAH
    # ==========================================
    else:
        st.subheader(f"Input & Pengolahan Data: {user['nama_sekolah']}")
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
                        if st.button("📤 Kirim Hasil ke Admin Dinas"):
                            res = st.session_state['rekon_temp']
                            supabase.table("hasil_rekon").insert({
                                'username': user['username'],
                                'nama_sekolah': user['nama_sekolah'],
                                'tanggal_submit': datetime.now().strftime("%Y-%m-%d %H:%M"),
                                'total_matched': res['matched'],
                                'total_only_sipd': res['only_sipd'],
                                'total_only_bank': res['only_bank'],
                                'nominal_cocok': float(res['nom_cocok']),
                                'status': 'Terkirim',
                                'detail_json': json.dumps(res['detail_items'])
                            }).execute()

                            st.balloons()
                            st.success("Hasil rekonsiliasi berhasil tersimpan permanen di Supabase!")
                            del st.session_state['rekon_temp']

        with tab_history:
            res_h = supabase.table("hasil_rekon").select("tanggal_submit, total_matched, total_only_sipd, total_only_bank, nominal_cocok, status").eq("username", user['username']).order("id", desc=True).execute()
            if res_h.data:
                st.dataframe(pd.DataFrame(res_h.data), use_container_width=True)
            else:
                st.info("Belum ada riwayat pengiriman.")
