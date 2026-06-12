import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io
from fpdf import FPDF
import altair as alt
import re

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Akıllı Aşı Lojistik Paneli", layout="wide")

st.title("💉 Akıllı Aşı Talep Tahmini ve Stok Yönetim Paneli")

# --- YARDIMCI FONKSİYONLAR ---
def clean_number(x):
    if isinstance(x, str):
        return x.replace('.', '').replace(',', '').replace('"', '').strip()
    return x

# Gelişmiş Tarih Okuyucu (Eski ve Yeni Dönem Formatlarını Destekler)
def get_dates_from_file(file_obj):
    file_ext = file_obj.name.split('.')[-1].lower()
    start_date, end_date = None, None
    single_date_pattern = re.compile(r'\d{2}\.\d{2}\.\d{4}')
    period_pattern = re.compile(r'(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})')
    
    lines = []
    if file_ext in ['xlsx', 'xls']:
        try:
            file_obj.seek(0)
            df_temp = pd.read_excel(file_obj, header=None, nrows=15)
            for i in range(len(df_temp)):
                row_vals = [str(x) for x in df_temp.iloc[i].values if pd.notnull(x)]
                lines.append(" ".join(row_vals))
        except: pass
    else:
        file_obj.seek(0)
        try:
            lines = [file_obj.readline().decode('utf-8') for _ in range(15)]
        except:
            file_obj.seek(0)
            lines = [file_obj.readline().decode('iso-8859-9') for _ in range(15)]
            
    for line in lines:
        line_upper = line.upper().replace('İ', 'I')
        # Yeni Format: DÖNEM: 01.05.2026 - 28.05.2026
        if "DÖNEM" in line_upper or "DONEM" in line_upper:
            m = period_pattern.search(line)
            if m:
                start_date, end_date = m.groups()
                break
        
        # Eski Format: Başlangıç ve Bitiş ayrı ayrı
        if "BASLANGIÇ TARIHI" in line_upper or "BAŞLANGIÇ TARİHİ" in line_upper:
            m = single_date_pattern.search(line)
            if m: start_date = m.group()
        if "BITIS TARIHI" in line_upper or "BİTİŞ TARİHİ" in line_upper:
            m = single_date_pattern.search(line)
            if m: end_date = m.group()

    if start_date and end_date:
        try:
            d1 = datetime.strptime(start_date, "%d.%m.%Y")
            d2 = datetime.strptime(end_date, "%d.%m.%Y")
            return (d2 - d1).days + 1, start_date, end_date
        except: pass
    return 91, None, None

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Rapor')
    return output.getvalue()

def tr_fix(text):
    if not isinstance(text, str):
        text = str(text)
    text = text.replace("🚨", "").replace("✅", "").replace("⚠️", "")
    rep = {"İ":"I","ı":"i","Ğ":"G","ğ":"g","Ş":"S","ş":"s","ç":"c","Ç":"C","ö":"o","Ö":"O","ü":"u","Ü":"U"}
    for k, v in rep.items():
        text = text.replace(k, v)
    return text.strip()

def to_pdf(df, title):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, tr_fix(title), ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 8)
    cols = df.columns.tolist()
    col_width = 190 / len(cols)
    
    for col in cols:
        pdf.cell(col_width, 8, tr_fix(str(col)), 1)
    pdf.ln()
    
    pdf.set_font("Helvetica", "", 7)
    for i in range(len(df)):
        for col in cols:
            val = tr_fix(str(df.iloc[i][col]))
            pdf.cell(col_width, 7, val[:25], 1)
        pdf.ln()
    
    return bytes(pdf.output())

# --- ÖZELLEŞTİRİLMİŞ YUVARLAMA FONKSİYONU ---
def ozellestirilmis_yuvarlama(val):
    if val <= 0: return 0
    def math_round(n): return int(n + 0.5)
    
    if val < 100: return math_round(val / 10) * 10
    elif val < 500: return math_round(val / 50) * 50
    else: return math_round(val / 100) * 100

# --- EVRENSEL VERİ OKUYUCU (EXCEL VE CSV) ---
def load_robust_data(file_obj, keywords):
    ext = file_obj.name.split('.')[-1].lower()
    
    # EXCEL İSE
    if ext in ['xlsx', 'xls']:
        file_obj.seek(0)
        try:
            df_temp = pd.read_excel(file_obj, header=None, nrows=20)
            header_idx = 0
            for i in range(len(df_temp)):
                row_str = " ".join([str(x).upper().replace('İ', 'I') for x in df_temp.iloc[i].values if pd.notnull(x)])
                if any(kw in row_str for kw in keywords):
                    header_idx = i
                    break
            file_obj.seek(0)
            df = pd.read_excel(file_obj, header=header_idx, dtype=str)
            return df
        except Exception as e:
            st.error(f"Excel okuma hatası: {e}")
            return pd.DataFrame()
            
    # CSV İSE
    else:
        file_obj.seek(0)
        header_idx = 0
        try:
            for i in range(25):
                raw_line = file_obj.readline()
                try: line = raw_line.decode('utf-8').upper().replace('İ', 'I')
                except: line = raw_line.decode('iso-8859-9', errors='ignore').upper().replace('İ', 'I')
                if any(kw in line for kw in keywords):
                    header_idx = i
                    break
        except: pass
        
        methods = [
            {'encoding': 'utf-8', 'sep': ';'},
            {'encoding': 'iso-8859-9', 'sep': ';'},
            {'encoding': 'utf-8', 'sep': ','},
            {'encoding': 'iso-8859-9', 'sep': ','},
            {'encoding': 'iso-8859-9', 'sep': ';', 'quoting': 3, 'on_bad_lines': 'skip'},
            {'encoding': 'iso-8859-9', 'sep': ',', 'quoting': 3, 'on_bad_lines': 'skip'},
            {'encoding': 'utf-8', 'sep': None, 'engine': 'python'}
        ]
        
        for m in methods:
            try:
                file_obj.seek(0)
                kw = {k: v for k, v in m.items() if k != 'encoding'}
                df = pd.read_csv(file_obj, header=header_idx, encoding=m['encoding'], dtype=str, **kw)
                if len(df.columns) > 1: return df
            except: continue
            
        file_obj.seek(0)
        return pd.read_csv(file_obj, header=header_idx, encoding='iso-8859-9', sep=';', dtype=str, on_bad_lines='skip')

# --- YAN MENÜ ---
st.sidebar.header("⚙️ Planlama Ayarları")

# 1. ANA AYAR
st.sidebar.markdown("**1. Planlama Periyodu**")
plan_suresi = st.sidebar.slider("Plan Süresi (Gün)", 1, 60, 10, help="Stokların kaç gün yetecek şekilde planlanacağını seçin.")

# 2. GELİŞMİŞ AYARLAR
st.sidebar.markdown("---")
with st.sidebar.expander("🛠️ Gelişmiş / İnce Ayarlar"):
    st.info("Bu parametreler kurumsal politikalarla ilgilidir.")
    guvenlik_marji = st.slider("Güvenlik Payı (%)", 0, 100, 20) / 100
    c1, c2 = st.columns(2)
    with c1:
        kritik_esik = st.number_input("Kritik (Gün)", value=3)
    with c2:
        asiri_esik = st.number_input("Aşırı (Gün)", value=60)

# --- DOSYA YÜKLEME ALANI ---
st.markdown("### 📂 Dosya Yükleme")
col_u1, col_u2, col_u3 = st.columns(3)
with col_u1:
    tuketim_file = st.file_uploader("📂 Tüketim Raporu", type=["csv", "xlsx", "xls"])
with col_u2:
    stok_file = st.file_uploader("📂 Stok Raporu", type=["csv", "xlsx", "xls"])
with col_u3:
    birim_file = st.file_uploader("📂 Birimler Listesi (Master)", type=["csv", "xlsx", "xls"])

# --- ANA PROGRAM ---
if tuketim_file and stok_file and birim_file:
    try:
        oto_gun_sayisi, s_tarih, b_tarih = get_dates_from_file(tuketim_file)
        
        # 1. MASTER BİRİMLER LİSTESİNİ YÜKLE VE HAZIRLA
        df_raw_b = load_robust_data(birim_file, ['BIRIM ADI', 'BIRIM TIPI', 'ILÇE'])
        df_raw_b.columns = [str(c).strip().upper().replace('İ', 'I') for c in df_raw_b.columns]
        
        rename_b = {}
        for col in df_raw_b.columns:
            if col == 'BIRIM ADI': rename_b[col] = 'BIRIM'
            elif col == 'BIRIM TIPI': rename_b[col] = 'TIP_MASTER'
            elif col == 'ILÇE': rename_b[col] = 'ILÇE_MASTER'
            elif col == 'UST BIRIM': rename_b[col] = 'UST_BIRIM_MASTER'
        df_raw_b.rename(columns=rename_b, inplace=True)
        
        req_cols = ['BIRIM']
        if 'TIP_MASTER' in df_raw_b.columns: req_cols.append('TIP_MASTER')
        if 'ILÇE_MASTER' in df_raw_b.columns: req_cols.append('ILÇE_MASTER')
        if 'UST_BIRIM_MASTER' in df_raw_b.columns: req_cols.append('UST_BIRIM_MASTER')
        
        birim_master = df_raw_b[req_cols].drop_duplicates(subset=['BIRIM']).copy()
        
        # 2. TÜKETİM VE STOK VERİLERİNİ YÜKLE
        # Tüketim raporu için yeni ve eski format başlıklarını destekleyen kelimeler eklendi
        df_raw_t = load_robust_data(tuketim_file, ['UYGULANAN', 'URUN', 'ÜRÜN'])
        df_raw_s = load_robust_data(stok_file, ['QR KOD', 'KALAN DOZ', 'TOPLAM DOZ', 'BIRIM ADI', 'BIRIM TIPI'])
        
        df_raw_t.columns = [str(c).strip() for c in df_raw_t.columns]
        df_raw_s.columns = [str(c).strip() for c in df_raw_s.columns]

        # --- SÜTUN ONARIMI ---
        def smart_fix_columns(df):
            rename_map = {}
            for col in df.columns:
                col_upper = col.upper().replace('İ', 'I')
                col_clean = col.replace('"', '').strip()
                if 'ZAYI' in col_upper: rename_map[col] = 'ZAYI'
                elif (col_upper.startswith('IL') or col_upper.startswith('İL')) and col_upper.endswith('E'): rename_map[col] = 'ILÇE'
                elif 'BIRIM' in col_upper and 'ADI' in col_upper: rename_map[col] = 'BIRIM'
                elif 'BIRIM' in col_upper and 'TIPI' in col_upper: rename_map[col] = 'BIRIM TIPI'
                elif col_upper == 'BIRIM' or col_upper == 'BİRİM': rename_map[col] = 'BIRIM'
                elif 'TAN' in col_upper and 'IMI' in col_upper: rename_map[col] = 'ÜRÜN TANIMI'
                elif 'TOPLAM' in col_upper and 'DOZ' in col_upper and 'UYGULANAN' not in col_upper and 'ZAYI' not in col_upper: rename_map[col] = 'TOPLAM DOZ'
            if rename_map: df.rename(columns=rename_map, inplace=True)
            return df

        df_raw_t = smart_fix_columns(df_raw_t)
        
        # YENİ EKLENEN: Özet/Toplam satırlarını filtrele ("İL TOPLAMI" ve "-")
        if 'ILÇE' in df_raw_t.columns:
            df_raw_t = df_raw_t[~df_raw_t['ILÇE'].astype(str).str.upper().str.contains('TOPLAM', na=False)]
        if 'BIRIM' in df_raw_t.columns:
            df_raw_t = df_raw_t[df_raw_t['BIRIM'] != '-']

        # --- STOK YENİ FORMAT (BARKODLU) KONTROLÜ ---
        stok_cols_upper = [str(c).upper().replace('İ', 'I') for c in df_raw_s.columns]
        if 'QR KOD' in stok_cols_upper or 'KALAN DOZ' in stok_cols_upper:
            rename_map_s = {}
            for col in df_raw_s.columns:
                cu = col.upper().replace('İ', 'I')
                if cu == 'BIRIM': rename_map_s[col] = 'BIRIM'
                elif cu == 'URUN' or cu == 'ÜRÜN': rename_map_s[col] = 'ÜRÜN TANIMI'
                elif cu == 'KALAN DOZ': rename_map_s[col] = 'TOPLAM DOZ'
            df_raw_s.rename(columns=rename_map_s, inplace=True)
            
            if 'TOPLAM DOZ' in df_raw_s.columns:
                df_raw_s['TOPLAM DOZ'] = pd.to_numeric(df_raw_s['TOPLAM DOZ'].astype(str).apply(clean_number), errors='coerce').fillna(0)
            else:
                df_raw_s['TOPLAM DOZ'] = 0
                
            if 'BIRIM' in df_raw_s.columns and 'ÜRÜN TANIMI' in df_raw_s.columns:
                df_raw_s = df_raw_s.groupby(['BIRIM', 'ÜRÜN TANIMI'], as_index=False)['TOPLAM DOZ'].sum()
        else:
            df_raw_s = smart_fix_columns(df_raw_s)
            if 'BIRIM ADI' in df_raw_s.columns: df_raw_s.rename(columns={'BIRIM ADI': 'BIRIM'}, inplace=True)

        # 3. VERİLERİ BİRİMLER LİSTESİ (MASTER) İLE SABİTLEME
        # Tüketim verisine İlçe ve Birim Tipini bas
        if 'ILÇE' in df_raw_t.columns: df_raw_t.drop(columns=['ILÇE'], inplace=True)
        if 'BIRIM TIPI' in df_raw_t.columns: df_raw_t.drop(columns=['BIRIM TIPI'], inplace=True)
        df_raw_t = pd.merge(df_raw_t, birim_master, on='BIRIM', how='left')
        if 'ILÇE_MASTER' in df_raw_t.columns: df_raw_t.rename(columns={'ILÇE_MASTER': 'ILÇE'}, inplace=True)
        if 'TIP_MASTER' in df_raw_t.columns: df_raw_t.rename(columns={'TIP_MASTER': 'BIRIM TIPI'}, inplace=True)
        
        # Stok verisine İlçe ve Birim Tipini bas
        if 'ILÇE' in df_raw_s.columns: df_raw_s.drop(columns=['ILÇE'], inplace=True)
        if 'BIRIM TIPI' in df_raw_s.columns: df_raw_s.drop(columns=['BIRIM TIPI'], inplace=True)
        df_raw_s = pd.merge(df_raw_s, birim_master, on='BIRIM', how='left')
        if 'ILÇE_MASTER' in df_raw_s.columns: df_raw_s.rename(columns={'ILÇE_MASTER': 'ILÇE'}, inplace=True)
        if 'TIP_MASTER' in df_raw_s.columns: df_raw_s.rename(columns={'TIP_MASTER': 'BIRIM TIPI'}, inplace=True)

        # Boşlukları doldur
        df_raw_t['ILÇE'] = df_raw_t['ILÇE'].fillna('BİLİNMİYOR')
        df_raw_s['ILÇE'] = df_raw_s['ILÇE'].fillna('BİLİNMİYOR')
        
        df_raw_t['Tuketim'] = pd.to_numeric(df_raw_t['UYGULANAN DOZ'].astype(str).apply(clean_number), errors='coerce').fillna(0) if 'UYGULANAN DOZ' in df_raw_t.columns else 0
        df_raw_t['Zayi'] = pd.to_numeric(df_raw_t['ZAYI'].astype(str).apply(clean_number), errors='coerce').fillna(0) if 'ZAYI' in df_raw_t.columns else 0

        stok_col = 'TOPLAM DOZ' if 'TOPLAM DOZ' in df_raw_s.columns else df_raw_s.columns[-1]
        df_raw_s['Stok'] = pd.to_numeric(df_raw_s[stok_col].astype(str).apply(clean_number), errors='coerce').fillna(0)

        # --- KRİTİK AYRIŞTIRMA (MASTER İLÇE VE İSİMLERE GÖRE) ---
        mask_ism_stok = (df_raw_s['ILÇE'].str.contains('FATIH', case=False, na=False)) & (df_raw_s['BIRIM'].str.contains('ISM', case=False, na=False))
        mask_ism_tuketim = (df_raw_t['ILÇE'].str.contains('FATIH', case=False, na=False)) & (df_raw_t['BIRIM'].str.contains('ISM', case=False, na=False))

        df_s_saha = df_raw_s[~mask_ism_stok].copy()
        df_t_saha = df_raw_t[~mask_ism_tuketim].copy()
        df_s_ism = df_raw_s[mask_ism_stok].copy()
        df_t_ism = df_raw_t[mask_ism_tuketim].copy()

        # --- GRUPLAMA VE BİRLEŞTİRME ---
        df_c = df_t_saha.groupby(['ILÇE', 'BIRIM', 'ÜRÜN TANIMI']).agg({'Tuketim': 'sum', 'Zayi': 'sum'}).reset_index()
        df_c.columns = ['Ilce', 'Birim', 'Urun', 'Tuketim', 'Zayi']
        
        df_s_grp = df_s_saha.groupby(['ILÇE', 'BIRIM', 'ÜRÜN TANIMI'])['Stok'].sum().reset_index()
        df_s_grp.columns = ['Ilce', 'Birim', 'Urun', 'Stok']
        
        res_df = pd.merge(df_c, df_s_grp, on=['Ilce', 'Birim', 'Urun'], how='outer').fillna(0)
        
        # Son tabloya Ana Tip ve Üst Birim bilgilerini kalıcı ekle
        bm_reduced = birim_master.rename(columns={'TIP_MASTER': 'Tip', 'UST_BIRIM_MASTER': 'Ust_Birim'})
        cols_to_merge = ['BIRIM']
        if 'Tip' in bm_reduced.columns: cols_to_merge.append('Tip')
        if 'Ust_Birim' in bm_reduced.columns: cols_to_merge.append('Ust_Birim')
        
        res_df = pd.merge(res_df, bm_reduced[cols_to_merge], left_on='Birim', right_on='BIRIM', how='left')
        res_df.drop(columns=['BIRIM'], inplace=True)
        
        def infer_tip(row):
            if pd.notnull(row.get('Tip')) and str(row.get('Tip')).strip() != '':
                return row['Tip']
            name = str(row['Birim']).upper()
            if 'ASM' in name or 'AILE SAGLIGI' in name: return 'ASM'
            if 'TSM' in name or 'TOPLUM SAGLIGI' in name: return 'TSM'
            if 'ISM' in name: return 'ISM'
            son_kullanici_keywords = ['HASTANE', 'ÖZEL', 'OZEL', 'GÖÇMEN', 'MÜLTECİ', 'VEREM', 'DISPANSER', 'BELEDIYE']
            if any(keyword in name for keyword in son_kullanici_keywords): return 'SON KULLANICI'
            return 'Bilinmiyor'

        res_df['Tip'] = res_df.apply(infer_tip, axis=1)
        if 'Ust_Birim' not in res_df.columns: res_df['Ust_Birim'] = '-'
        res_df['Ust_Birim'] = res_df['Ust_Birim'].fillna('-')

        res_df['Gunluk_Hiz'] = res_df['Tuketim'] / oto_gun_sayisi
        
        # --- ANOMALİ (HATALI VERİ) DEDEKTÖRÜ MANTIĞI ---
        def anomali_tespit(row):
            hiz = row['Gunluk_Hiz']
            tip = str(row['Tip']).upper()
            
            if 'ASM' in tip and hiz > 30: return True
            elif 'TSM' in tip and hiz > 150: return True
            elif 'SON KULLANICI' in tip and hiz > 150: return True
            elif hiz > 500: return True
            return False

        res_df['Veri_Anomalisi'] = res_df.apply(anomali_tespit, axis=1)

        # --- İHTİYAÇ VE YUVARLAMA ---
        res_df['Ihtiyac'] = ((res_df['Gunluk_Hiz'] * plan_suresi) * (1 + guvenlik_marji)) - res_df['Stok']
        res_df['Gonderilecek'] = res_df['Ihtiyac'].apply(ozellestirilmis_yuvarlama)
        
        res_df['Yetme_Suresi'] = res_df.apply(lambda r: round(r['Stok'] / r['Gunluk_Hiz'], 1) if r['Gunluk_Hiz'] > 0 else 999, axis=1)

        def get_durum_ve_fazla(row):
            if row['Yetme_Suresi'] < kritik_esik: durum = "🚨 KRİTİK"
            elif row['Yetme_Suresi'] > asiri_esik:
                tip_str = str(row['Tip']).upper()
                durum = "⚠️ AŞIRI" if any(x in tip_str for x in ['ASM', 'SON KULLANICI']) else "✅ Yeterli"
            else: durum = "✅ Yeterli"
            hedef_stok = row['Gunluk_Hiz'] * asiri_esik
            fazla_miktar = max(0, row['Stok'] - hedef_stok)
            return pd.Series([durum, int(fazla_miktar)])

        res_df[['Durum', 'Fazla_Miktar']] = res_df.apply(get_durum_ve_fazla, axis=1)

        # --- FİLTRELER ---
        st.sidebar.markdown("---")
        st.sidebar.markdown("**🔍 Veri Filtreleme**")
        sec_ilce = st.sidebar.multiselect("📍 İlçe Filtrele", options=sorted(res_df['Ilce'].unique()))
        sec_asi = st.sidebar.multiselect("💉 Aşı Filtrele", options=sorted(res_df['Urun'].unique()))
        
        df_f = res_df.copy()
        if sec_ilce: df_f = df_f[df_f['Ilce'].isin(sec_ilce)]
        if sec_asi: df_f = df_f[df_f['Urun'].isin(sec_asi)]
        
        # --- İL GENELİ VERİSİ HAZIRLIĞI ---
        grp_tuketim_saha = df_t_saha.groupby('ÜRÜN TANIMI')['Tuketim'].sum()
        grp_stok_saha = df_s_saha.groupby('ÜRÜN TANIMI')['Stok'].sum()
        grp_stok_ism = df_s_ism.groupby('ÜRÜN TANIMI')['Stok'].sum()
        grp_tuketim_ism = df_t_ism.groupby('ÜRÜN TANIMI')['Tuketim'].sum() 
        grp_tuketim_total = grp_tuketim_saha.add(grp_tuketim_ism, fill_value=0)
        
        all_vaccines = grp_stok_saha.index.union(grp_stok_ism.index).union(grp_tuketim_total.index)
        df_genel = pd.DataFrame(index=all_vaccines)
        df_genel.index.name = 'Urun'
        df_genel['İl Ana Depo (ISM)'] = grp_stok_ism
        df_genel['Saha (TSM, ASM, Son)'] = grp_stok_saha
        df_genel['Toplam Tüketim'] = grp_tuketim_total
        df_genel = df_genel.fillna(0)
        df_genel['İl Geneli Stok'] = df_genel['İl Ana Depo (ISM)'] + df_genel['Saha (TSM, ASM, Son)']
        df_genel['Günlük ortalama tüketim'] = (df_genel['Toplam Tüketim'] / oto_gun_sayisi).round(2)
        df_genel['Yetme Süresi (Gün)'] = df_genel.apply(lambda r: round(r['İl Geneli Stok'] / r['Günlük ortalama tüketim'], 1) if r['Günlük ortalama tüketim'] > 0 else 999, axis=1)
        
        if s_tarih: st.info(f"📅 **Dönemsel Tüketim Raporu:** {s_tarih} - {b_tarih} ({oto_gun_sayisi} Gün)")

        toplam_sevk = int(df_f[df_f['Gonderilecek'] > 0]['Gonderilecek'].sum())
        kritik_sayisi = len(df_f[df_f['Durum'] == "🚨 KRİTİK"])
        asiri_sayisi = len(df_f[df_f['Durum'] == "⚠️ AŞIRI"])
        kurum_sayisi = df_f[df_f['Gonderilecek'] > 0]['Birim'].nunique()
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("📦 SEVKİYAT (DOZ)", f"{toplam_sevk:,}".replace(",", "."))
        m2.metric("🚨 KRİTİK STOK", kritik_sayisi)
        m3.metric("⚠️ AŞIRI STOK", asiri_sayisi)
        m4.metric("🏢 KURUM SAYISI", kurum_sayisi)
        
        st.markdown("---")

        # --- SEKMELER ---
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📊 İl Geneli",
            "📍 İlçe Bazlı Özet",
            "📦 Sevkiyat Planı",
            "⚠️ Fazla ve Ölü Stok",
            "🔄 Akıllı Transfer",
            "📉 Zayi ve Verimlilik"
        ])

        # TAB 1: İL GENELİ
        with tab1:
            st.subheader("📊 İl Geneli Toplam Stok ve Tüketim Analizi")
            
            df_genel['İl Ana Depo Yetme Süresi (Gün)'] = df_genel.apply(lambda r: round(r['İl Ana Depo (ISM)'] / r['Günlük ortalama tüketim'], 1) if r['Günlük ortalama tüketim'] > 0 else 999, axis=1)
            df_genel = df_genel.reset_index()
            cols_order = ['Urun', 'İl Geneli Stok', 'İl Ana Depo (ISM)', 'İl Ana Depo Yetme Süresi (Gün)', 'Saha (TSM, ASM, Son)', 'Toplam Tüketim', 'Günlük ortalama tüketim', 'Yetme Süresi (Gün)']
            if 'Urun' not in df_genel.columns: df_genel.rename(columns={df_genel.columns[0]: 'Urun'}, inplace=True)
            df_genel = df_genel[cols_order]

            st.markdown("### ⏳ Aşı Bazlı Yetme Süresi Analizi")
            chart_df = df_genel.copy()
            chart_df['Visual_Value'] = chart_df['Yetme Süresi (Gün)'].apply(lambda x: 180 if x > 180 else x)
            chart_df['Label'] = chart_df['Yetme Süresi (Gün)'].apply(lambda x: "180+" if x > 180 else f"{x:.1f}")
            chart_df['Color'] = chart_df['Yetme Süresi (Gün)'].apply(lambda val: '#ff4b4b' if val < 15 else '#ffa500' if val < 30 else '#ffe066' if val < 60 else '#90ee90')
            
            base = alt.Chart(chart_df).encode(x=alt.X('Urun', sort='-y', title='Aşılar'), tooltip=['Urun', 'Yetme Süresi (Gün)', 'İl Geneli Stok', 'Günlük ortalama tüketim'])
            bars = base.mark_bar().encode(y=alt.Y('Visual_Value', title='Yetme Süresi (Gün) [Maks 180]'), color=alt.Color('Color', scale=None, legend=None))
            text = base.mark_text(align='center', baseline='bottom', dy=-5).encode(y='Visual_Value', text='Label')
            st.altair_chart((bars + text).properties(height=400).interactive(), use_container_width=True)

            def highlight_yetme_suresi(val):
                if not isinstance(val, (int, float)): return ''
                if val < 15: return 'background-color: #ff4b4b; color: white'
                elif val < 30: return 'background-color: #ffa500; color: black'
                elif val < 60: return 'background-color: #ffe066; color: black'
                else: return 'background-color: #90ee90; color: black'

            styled_df = df_genel.style.map(highlight_yetme_suresi, subset=['Yetme Süresi (Gün)', 'İl Ana Depo Yetme Süresi (Gün)'])
            styled_df = styled_df.format({"Günlük ortalama tüketim": "{:.2f}", "Yetme Süresi (Gün)": "{:.1f}", "İl Ana Depo Yetme Süresi (Gün)": "{:.1f}", "İl Geneli Stok": "{:.0f}", "İl Ana Depo (ISM)": "{:.0f}", "Saha (TSM, ASM, Son)": "{:.0f}", "Toplam Tüketim": "{:.0f}"})
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
            c7, c8 = st.columns(2)
            with c7: st.download_button("📥 İl Geneli Excel", to_excel(df_genel), "il_geneli_ozet.xlsx")
            with c8: st.download_button("📥 İl Geneli PDF", to_pdf(df_genel, "Il Geneli Stok ve Tuketim"), "il_geneli_ozet.pdf")

        # TAB 2: İLÇE BAZLI
        with tab2:
            df_i = df_f.groupby(['Ilce', 'Urun']).agg({'Tuketim': 'sum', 'Stok': 'sum'}).reset_index()
            df_i['Ihtiyac'] = (((df_i['Tuketim'] / oto_gun_sayisi) * plan_suresi) * (1 + guvenlik_marji)) - df_i['Stok']
            
            df_i['Gonderilecek'] = df_i['Ihtiyac'].apply(ozellestirilmis_yuvarlama)

            f2_visible = df_i[df_i['Gonderilecek'] > 0].copy().sort_values(['Ilce', 'Gonderilecek'], ascending=[True, False])
            
            if not f2_visible.empty:
                sum_row = pd.DataFrame({'Ilce': ['TOPLAM'], 'Urun': ['-'], 'Tuketim': [f2_visible['Tuketim'].sum()], 'Stok': [f2_visible['Stok'].sum()], 'Ihtiyac': [f2_visible['Ihtiyac'].sum()], 'Gonderilecek': [f2_visible['Gonderilecek'].sum()]})
                f2_display = pd.concat([f2_visible, sum_row], ignore_index=True)
            else: f2_display = f2_visible

            st.subheader("İlçe Bazlı Toplam İhtiyaçlar")
            st.dataframe(f2_display, use_container_width=True)
            c5, c6 = st.columns(2)
            with c5: st.download_button("📥 İlçe Excel", to_excel(f2_display), "ilce_ozet.xlsx")
            with c6: st.download_button("📥 İlçe PDF", to_pdf(f2_display, "Ilce Ozet"), "ilce_ozet.pdf")

        # TAB 3: SEVKİYAT PLANI
        with tab3:
            
            df_anomali = df_f[(df_f['Veri_Anomalisi'] == True) & (df_f['Gonderilecek'] > 0)].copy()
            
            if not df_anomali.empty:
                st.error("🚨 **DİKKAT: Olası Hatalı Veri Girişi Tespit Edildi!**")
                st.markdown("""
                Aşağıdaki birimlerin **günlük aşı tüketim hızları**, bulundukları kurum tipinin (ASM vb.) rutin ortalamalarına göre **şüpheli derecede yüksektir.** Sahadaki personeller sisteme hatalı veri girmiş olabilir. 
                *Yanlışlıkla çok yüksek miktarda aşı sevkiyatı yapmamak için, bu kurumlara gönderim yapmadan önce **telefonla arayarak teyit etmeniz** önerilir.*
                """)
                st.dataframe(df_anomali[['Ilce', 'Ust_Birim', 'Birim', 'Urun', 'Tip', 'Gunluk_Hiz', 'Tuketim', 'Gonderilecek']].style.format({'Gunluk_Hiz': '{:.1f}'}), use_container_width=True)
                st.markdown("---")

            st.caption("Aşağıdaki liste sadece aşı gönderilmesi gereken (İhtiyaç > 0) kurumları içerir.")
            f1_sevk = df_f[df_f['Gonderilecek'] > 0].copy()
            durum_sirasi = {"🚨 KRİTİK": 0, "✅ Yeterli": 1, "⚠️ AŞIRI": 2}
            f1_sevk['sort_key'] = f1_sevk['Durum'].map(durum_sirasi)
            f1_sevk = f1_sevk.sort_values(['sort_key', 'Gonderilecek'], ascending=[True, False]).drop('sort_key', axis=1)
            
            st.dataframe(f1_sevk[['Durum', 'Ilce', 'Ust_Birim', 'Birim', 'Urun', 'Tuketim', 'Stok', 'Gonderilecek', 'Yetme_Suresi']], use_container_width=True)
            c1, c2 = st.columns(2)
            with c1: st.download_button("📥 Sevkiyat Excel", to_excel(f1_sevk), "sevkiyat_plani.xlsx")
            with c2: st.download_button("📥 Sevkiyat PDF", to_pdf(f1_sevk, "Sevkiyat Plani"), "sevkiyat_plani.pdf")

        # TAB 4: FAZLA VE ÖLÜ STOK
        with tab4:
            st.caption(f"Aşağıdaki liste, {asiri_esik} günden fazla stoğu bulunan ve 'Aşırı' olarak işaretlenen **ASM ve Son Kullanıcı** birimlerini içerir.")
            f1_asiri = df_f[df_f['Durum'] == "⚠️ AŞIRI"].copy().sort_values('Yetme_Suresi', ascending=False)
            st.dataframe(f1_asiri[['Ilce', 'Ust_Birim', 'Birim', 'Urun', 'Stok', 'Yetme_Suresi']], use_container_width=True)
            c3, c4 = st.columns(2)
            with c3: st.download_button("📥 İade Excel", to_excel(f1_asiri), "asiri_stok.xlsx")
            with c4: st.download_button("📥 İade PDF", to_pdf(f1_asiri, "Asiri Stok"), "asiri_stok.pdf")
            
            st.markdown("---")
            st.subheader("🕸️ Ölü Stok (Hiç Tüketimi Olmayan)")
            f1_olu = df_f[(df_f['Stok'] > 0) & (df_f['Tuketim'] == 0) & (df_f['Tip'].astype(str).str.upper().apply(lambda x: any(k in x for k in ['ASM', 'SON KULLANICI'])))].copy().sort_values('Stok', ascending=False)
            if not f1_olu.empty:
                st.dataframe(f1_olu[['Ilce', 'Ust_Birim', 'Birim', 'Urun', 'Stok']], use_container_width=True)
                c_olu1, c_olu2 = st.columns(2)
                with c_olu1: st.download_button("📥 Ölü Stok Excel", to_excel(f1_olu), "olu_stok.xlsx")
                with c_olu2: st.download_button("📥 Ölü Stok PDF", to_pdf(f1_olu, "Olu Stok"), "olu_stok.pdf")
            else: st.success("Tebrikler! Ölü stok (hareketsiz ürün) bulunamadı.")

        # TAB 5: AKILLI TRANSFER
        with tab5:
            st.subheader("🔄 Akıllı Transfer Önerileri (İlçe İçi)")
            transfer_oncelik = st.radio(
                "Transfer Hedefi Önceliği Seçiniz:",
                ["Tümü (Genel)", "Sadece ASM'ler (Aile Sağlığı Merkezleri)", "Sadece Son Kullanıcı Birimleri"],
                horizontal=True
            )
            st.markdown("Bu modül, aynı ilçe içinde **fazla stoğu olan** birimlerle **aşı ihtiyacı olan** birimleri eşleştirir.")
            
            transfer_onerileri = []
            for ilce in df_f['Ilce'].unique():
                df_ilce = df_f[df_f['Ilce'] == ilce]
                df_ilce_transfer = df_ilce[~df_ilce['Tip'].astype(str).str.upper().apply(lambda x: any(k in x for k in ['ISM', 'TSM', 'DEPO']))].copy()
                
                for urun in df_ilce_transfer['Urun'].unique():
                    alicilar = df_ilce_transfer[(df_ilce_transfer['Urun'] == urun) & (df_ilce_transfer['Gonderilecek'] > 0)].copy()
                    if transfer_oncelik == "Sadece ASM'ler (Aile Sağlığı Merkezleri)":
                        alicilar = alicilar[alicilar['Tip'].astype(str).str.upper().str.contains("ASM")]
                    elif transfer_oncelik == "Sadece Son Kullanıcı Birimleri":
                        alicilar = alicilar[alicilar['Tip'].astype(str).str.upper().str.contains("SON KULLANICI")]
                    
                    vericiler = df_ilce_transfer[(df_ilce_transfer['Urun'] == urun) & (df_ilce_transfer['Fazla_Miktar'] > 0)].copy()
                    
                    if alicilar.empty or vericiler.empty: continue
                    vericiler = vericiler.sort_values('Fazla_Miktar', ascending=False)
                    alicilar = alicilar.sort_values('Gonderilecek', ascending=False)
                    
                    for _, verici in vericiler.iterrows():
                        if verici['Fazla_Miktar'] <= 0: continue
                        for idx_alici, alici in alicilar.iterrows():
                            if alici['Gonderilecek'] <= 0: continue
                            transfer_miktar = min(verici['Fazla_Miktar'], alici['Gonderilecek'])
                            if transfer_miktar >= 10:
                                transfer_onerileri.append({
                                    'İlçe': ilce, 'Ürün': urun,
                                    'Kimden (Verici)': verici['Birim'], 'Tip (Verici)': verici['Tip'],
                                    'Kime (Alıcı)': alici['Birim'], 'Tip (Alıcı)': alici['Tip'],
                                    'Transfer Miktarı': int(transfer_miktar)
                                })
                                verici['Fazla_Miktar'] -= transfer_miktar
                                alicilar.at[idx_alici, 'Gonderilecek'] -= transfer_miktar

            if transfer_onerileri:
                df_transfer = pd.DataFrame(transfer_onerileri)
                st.success(f"Toplam {len(df_transfer)} adet (10 Doz+) transfer önerisi bulundu. ({transfer_oncelik})")
                st.dataframe(df_transfer, use_container_width=True)
                c_tr1, c_tr2 = st.columns(2)
                with c_tr1: st.download_button("📥 Transfer Önerileri Excel", to_excel(df_transfer), "akilli_transfer.xlsx")
                with c_tr2: st.download_button("📥 Transfer Önerileri PDF", to_pdf(df_transfer, "Akilli Transfer Onerileri"), "akilli_transfer.pdf")
            else:
                st.info(f"Seçilen kriterlere göre ({transfer_oncelik}, En az 10 doz) transfer fırsatı bulunamadı.")

        # TAB 6: ZAYİ VE VERİMLİLİK
        with tab6:
            st.subheader("📉 Zayi ve Verimlilik Analizi")
            analiz_turu = st.radio("Analiz Türü Seçin:", ("Tüm Aşılar (Genel Görünüm)", "Sadece Tekli Doz Aşılar (Kritik Analiz)"), horizontal=True)
            df_zayi = df_f.copy()
            if analiz_turu == "Sadece Tekli Doz Aşılar (Kritik Analiz)": df_zayi = df_zayi[~df_zayi['Urun'].str.upper().str.contains('BCG|POLIO|PPD', regex=True)]

            zayi_ozet = df_zayi.groupby('Ilce').agg({'Tuketim': 'sum', 'Zayi': 'sum'}).reset_index()
            zayi_ozet['Zayi Oranı (%)'] = zayi_ozet.apply(lambda x: (x['Zayi'] / (x['Tuketim'] + x['Zayi']) * 100) if (x['Tuketim'] + x['Zayi']) > 0 else 0, axis=1).round(2)
            zayi_ozet = zayi_ozet.sort_values('Zayi', ascending=False)
            
            col_z1, col_z2 = st.columns(2)
            with col_z1:
                st.markdown("#### 🏙️ İlçelere Göre Zayi Durumu")
                st.dataframe(zayi_ozet, use_container_width=True, hide_index=True)
            with col_z2:
                st.markdown("#### 💉 Aşılara Göre Toplam Zayi")
                asi_zayi = df_zayi.groupby('Urun')['Zayi'].sum().reset_index().sort_values('Zayi', ascending=False)
                st.dataframe(asi_zayi, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.markdown(f"#### 🏢 En Çok Zayi Veren 20 Kurum ({analiz_turu})")
            kurum_zayi = df_zayi.groupby(['Ilce', 'Birim', 'Urun']).agg({'Zayi': 'sum'}).reset_index()
            kurum_zayi = kurum_zayi[kurum_zayi['Zayi'] > 0].sort_values('Zayi', ascending=False).head(20)
            st.dataframe(kurum_zayi, use_container_width=True, hide_index=True)
            
            c9, c10 = st.columns(2)
            with c9: st.download_button("📥 Zayi Analizi Excel", to_excel(zayi_ozet), "zayi_analizi.xlsx")
            with c10: st.download_button("📥 Zayi Analizi PDF", to_pdf(zayi_ozet, "Zayi Analizi"), "zayi_analizi.pdf")
            
            st.markdown("---")
            st.markdown("### 📥 Detaylı Zayi Raporu (İlçe + Aşı Bazlı)")
            zayi_detay = df_zayi.groupby(['Ilce', 'Urun']).agg({'Tuketim': 'sum', 'Zayi': 'sum'}).reset_index()
            zayi_detay['Zayi Oranı (%)'] = zayi_detay.apply(lambda x: (x['Zayi'] / (x['Tuketim'] + x['Zayi']) * 100) if (x['Tuketim'] + x['Zayi']) > 0 else 0, axis=1).round(2)
            zayi_detay = zayi_detay.sort_values(['Ilce', 'Zayi'], ascending=[True, False])
            st.download_button("📥 Detaylı Zayi Raporu İndir (İlçe + Aşı)", to_excel(zayi_detay), "detayli_zayi_analizi.xlsx")

    except Exception as e:
        st.error(f"Hata: {e}")
else:
    st.info("Lütfen dosyaları yükleyin. (3 dosya da gereklidir)")
