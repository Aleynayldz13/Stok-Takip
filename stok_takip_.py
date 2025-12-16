import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import sqlite3
import csv
import os
from contextlib import contextmanager

# ==========================================
# AYARLAR VE VERİTABANI BAĞLANTISI
# ==========================================

# Kodu çalıştırdığınız klasördeki 'malzeme_takip_v2.db' dosyasını otomatik bulur.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "malzeme_takip_v2.db")

@contextmanager
def veritabani_baglantisi():
    """SQLite bağlantısını yöneten güvenli yapı."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
    except sqlite3.Error as e:
        messagebox.showerror("Veritabanı Hatası", f"Bağlantı hatası: {e}")
        if conn: conn.rollback()
        raise
    finally:
        if conn: conn.close()

# ==========================================
# 1. VERİTABANI KATMANI (Backend)
# ==========================================

class Veritabani:
    def __init__(self):
        # Eğer dosya yoksa tabloları oluşturur, varsa mevcut olana dokunmaz.
        self._tablo_olustur()
        
        # Veritabanı boş mu kontrol et, boşsa örnek veri ekle (Mevcut DB kullanıldığı için burası atlanacak)
        self._baslangic_kontrol()

    def _tablo_olustur(self):
        with veritabani_baglantisi() as conn:
            cursor = conn.cursor()
            # Yüklediğiniz dosyadaki şema ile birebir aynı yapı
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS malzemeler (
                    id INTEGER PRIMARY KEY,
                    ad TEXT NOT NULL UNIQUE,
                    miktar REAL NOT NULL,
                    kritik_esik INTEGER NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tarifler (
                    urun_ad TEXT NOT NULL,
                    malzeme_id INTEGER NOT NULL,
                    kullanilan_adet REAL NOT NULL,
                    PRIMARY KEY (urun_ad, malzeme_id),
                    FOREIGN KEY (malzeme_id) REFERENCES malzemeler(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS islem_gecmisi (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tarih TEXT DEFAULT (datetime('now', 'localtime')),
                    islem_tipi TEXT NOT NULL,
                    aciklama TEXT,
                    miktar_degisim REAL
                )
            """)
            conn.commit()

    def _baslangic_kontrol(self):
        """Veritabanı doluysa örnek veri eklemeyi atlar."""
        with veritabani_baglantisi() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT count(*) FROM malzemeler")
                sayi = cursor.fetchone()[0]
                if sayi == 0:
                    self._ornek_veri_ekle()
            except:
                pass

    def _ornek_veri_ekle(self):
        # Sadece veritabanı sıfırdan oluşturulursa çalışır
        with veritabani_baglantisi() as conn:
            cursor = conn.cursor()
            ornek_malzemeler = [
                ("Beyaz Kumaş (metre)", 100.0, 20), 
                ("Düğme Seti (Adet)", 50.0, 15), 
                ("Renkli İplik (Makara)", 30.0, 5),
                ("Fermuar (Adet)", 10.0, 5), 
            ]
            for ad, miktar, esik in ornek_malzemeler:
                try:
                    cursor.execute("INSERT INTO malzemeler (ad, miktar, kritik_esik) VALUES (?, ?, ?)", 
                                   (ad, miktar, esik))
                except sqlite3.IntegrityError: pass
            conn.commit()

    # --- OKUMA VE YAZMA FONKSİYONLARI ---

    def malzemeleri_oku(self):
        with veritabani_baglantisi() as conn:
            cursor = conn.cursor()
            # Kritik stoktakiler (miktar <= esik) listenin en başında görünür
            cursor.execute("""
                SELECT id, ad, miktar, kritik_esik 
                FROM malzemeler 
                ORDER BY (miktar <= kritik_esik) DESC, ad ASC
            """)
            return cursor.fetchall()

    def tarifleri_cek(self):
        with veritabani_baglantisi() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT urun_ad FROM tarifler ORDER BY urun_ad")
            return [row[0] for row in cursor.fetchall()]

    def tarif_bilesenlerini_cek(self, urun_ad):
        with veritabani_baglantisi() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.malzeme_id, m.ad, t.kullanilan_adet 
                FROM tarifler t
                INNER JOIN malzemeler m ON t.malzeme_id = m.id
                WHERE t.urun_ad = ?
            """, (urun_ad,))
            return cursor.fetchall()

    def kritik_sayisi_hesapla(self):
        with veritabani_baglantisi() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM malzemeler WHERE miktar <= kritik_esik")
            return cursor.fetchone()[0]

    def islem_gecmisi_oku(self):
        with veritabani_baglantisi() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, tarih, islem_tipi, aciklama, miktar_degisim FROM islem_gecmisi ORDER BY id DESC LIMIT 100")
            return cursor.fetchall()

    def islem_kaydet(self, islem_tipi, aciklama, miktar_degisim=0):
        try:
            with veritabani_baglantisi() as conn:
                conn.execute("INSERT INTO islem_gecmisi (islem_tipi, aciklama, miktar_degisim) VALUES (?, ?, ?)", 
                             (islem_tipi, aciklama, miktar_degisim))
                conn.commit()
        except: pass

    # --- İŞLEM FONKSİYONLARI ---

    def siparis_isleme_ve_stok_dus(self, urun_adi, siparis_miktari):
        """
        Database Locked hatasını önleyen tek-transaction yapısı.
        """
        with veritabani_baglantisi() as conn:
            cursor = conn.cursor()
            
            # 1. Reçete Kontrolü
            cursor.execute("SELECT malzeme_id, kullanilan_adet FROM tarifler WHERE urun_ad = ?", (urun_adi,))
            tarif_listesi = cursor.fetchall()
            
            if not tarif_listesi:
                return f"Uyarı: '{urun_adi}' için reçete/bileşen bulunamadı."

            # 2. Stok Yeterlilik Kontrolü
            yetersiz = []
            for mid, adet in tarif_listesi:
                gerekli = adet * siparis_miktari
                cursor.execute("SELECT ad, miktar FROM malzemeler WHERE id = ?", (mid,))
                res = cursor.fetchone()
                if res:
                    ad, stok = res
                    if stok < gerekli:
                        yetersiz.append(f"- {ad}: Mevcut {stok}, Gerekli {gerekli:.2f}")

            if yetersiz:
                return "YETERSİZ STOK:\n" + "\n".join(yetersiz)

            # 3. Stok Düşme ve Kayıt (Aynı bağlantıda)
            try:
                for mid, adet in tarif_listesi:
                    dusulecek = adet * siparis_miktari
                    cursor.execute("UPDATE malzemeler SET miktar = miktar - ? WHERE id = ?", (dusulecek, mid))
                
                aciklama = f"'{urun_adi}' ({siparis_miktari} adet) üretildi."
                cursor.execute("INSERT INTO islem_gecmisi (islem_tipi, aciklama, miktar_degisim) VALUES (?, ?, ?)", 
                             ("SİPARİŞ", aciklama, 0))
                
                conn.commit()
                return True
            except Exception as e:
                return f"İşlem sırasında hata: {e}"

    def malzeme_ekle(self, ad, miktar, kritik_esik):
        try:
            with veritabani_baglantisi() as conn:
                conn.execute("INSERT INTO malzemeler (ad, miktar, kritik_esik) VALUES (?, ?, ?)", 
                               (ad, miktar, kritik_esik))
                conn.commit()
            self.islem_kaydet("YENİ MALZEME", f"'{ad}' eklendi.", miktar)
            return True
        except sqlite3.IntegrityError:
            return f"Hata: '{ad}' isimli malzeme zaten kayıtlı."
        except Exception as e:
            return f"Veritabanı hatası: {e}"

    def malzeme_kaldir(self, malzeme_id):
        try:
            ad = "Bilinmeyen"
            with veritabani_baglantisi() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ad FROM malzemeler WHERE id=?", (malzeme_id,))
                res = cursor.fetchone()
                if res: ad = res[0]
                conn.execute("DELETE FROM malzemeler WHERE id = ?", (malzeme_id,))
                conn.commit()
            self.islem_kaydet("SİLME", f"'{ad}' silindi.")
            return True
        except Exception as e:
            return f"Hata: {e}"

    def stok_guncelle(self, id_val, miktar_degisim):
        try:
            ad = ""
            with veritabani_baglantisi() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ad, miktar FROM malzemeler WHERE id = ?", (id_val,))
                sonuc = cursor.fetchone()
                if sonuc:
                    ad, mevcut_miktar = sonuc
                    yeni_miktar = mevcut_miktar + miktar_degisim
                    if yeni_miktar < 0:
                        return f"Hata: '{ad}' stoğu negatife düşemez."
                    conn.execute("UPDATE malzemeler SET miktar = ? WHERE id = ?", (yeni_miktar, id_val))
                    conn.commit()
                else:
                    return "Malzeme bulunamadı."
            self.islem_kaydet("STOK GÜNCELLEME", f"'{ad}' güncellendi.", miktar_degisim)
            return True
        except Exception as e:
            return f"Hata: {e}"

    def tarif_bilesen_ekle(self, urun_ad, malzeme_id, kullanilan_adet):
        try:
            with veritabani_baglantisi() as conn:
                conn.execute("INSERT OR REPLACE INTO tarifler VALUES (?, ?, ?)", (urun_ad, malzeme_id, kullanilan_adet))
                conn.commit()
                return True
        except Exception as e:
            return str(e)

    def recete_bileseni_kaldir(self, urun_ad, malzeme_id):
        try:
            with veritabani_baglantisi() as conn:
                conn.execute("DELETE FROM tarifler WHERE urun_ad = ? AND malzeme_id = ?", (urun_ad, malzeme_id))
                conn.commit()
                return True
        except Exception:
            return False

    def recete_sil(self, urun_ad):
        try:
            with veritabani_baglantisi() as conn:
                conn.execute("DELETE FROM tarifler WHERE urun_ad = ?", (urun_ad,))
                conn.commit()
                return True
        except Exception:
            return False
            
    def gecmisi_temizle(self):
        try:
            with veritabani_baglantisi() as conn:
                conn.execute("DELETE FROM islem_gecmisi")
                conn.execute("DELETE FROM sqlite_sequence WHERE name='islem_gecmisi'")
                conn.commit()
                return True
        except Exception as e:
            return f"Hata: {e}"


# ==========================================
# 2. ARAYÜZ KATMANI
# ==========================================

class MalzemeTakipUygulamasi:
    def __init__(self, master):
        self.master = master
        master.title("Stok ve Reçete Yönetim Sistemi")
        master.geometry("1200x800")
        
        # Tema Renkleri
        self.RENKLER = {
            "bg_ana": "#f4f6f9",        
            "bg_sidebar": "#2c3e50",    
            "bg_panel": "#ffffff",      
            "primary": "#3498db",       
            "primary_hover": "#2980b9", 
            "success": "#2ecc71",       
            "success_hover": "#27ae60",
            "danger": "#e74c3c",        
            "danger_hover": "#c0392b",
            "text_dark": "#34495e",     
            "text_light": "#bdc3c7",    
            "table_header": "#dfe6e9",  
        }
        
        master.configure(bg=self.RENKLER["bg_ana"])

        self.db = Veritabani()
        self._stilleri_tanimla()
        self._arayuz_olustur()
        self.veri_yenile() 
        self.notebook.select(self.tab_index_map['Stok İşlemleri'])

    def _stilleri_tanimla(self):
        self.stil = ttk.Style()
        self.stil.theme_use('clam') 
        self.stil.configure(".", background=self.RENKLER["bg_ana"], foreground=self.RENKLER["text_dark"], font=('Segoe UI', 10))
        self.stil.configure("TFrame", background=self.RENKLER["bg_ana"])
        self.stil.configure("TLabel", background=self.RENKLER["bg_ana"], foreground=self.RENKLER["text_dark"])
        self.stil.configure("Sidebar.TFrame", background=self.RENKLER["bg_sidebar"])
        self.stil.configure("Sidebar.TLabel", background=self.RENKLER["bg_sidebar"], foreground=self.RENKLER["text_light"])
        self.stil.configure("SidebarHeader.TLabel", background=self.RENKLER["bg_sidebar"], foreground="white", font=('Segoe UI', 18, 'bold'))
        self.stil.configure("SidebarCard.TLabelframe", background=self.RENKLER["bg_sidebar"], borderwidth=1, relief="solid")
        self.stil.configure("Card.TFrame", background=self.RENKLER["bg_panel"], relief="flat")
        self.stil.configure("Card.TLabel", background=self.RENKLER["bg_panel"], foreground=self.RENKLER["text_dark"])
        self.stil.configure("Primary.TButton", background=self.RENKLER["primary"], foreground="white", borderwidth=0, font=('Segoe UI', 10, 'bold'))
        self.stil.map("Primary.TButton", background=[('active', self.RENKLER["primary_hover"])]) 
        self.stil.configure("Success.TButton", background=self.RENKLER["success"], foreground="white", borderwidth=0, font=('Segoe UI', 10, 'bold'))
        self.stil.map("Success.TButton", background=[('active', self.RENKLER["success_hover"])])
        self.stil.configure("Danger.TButton", background=self.RENKLER["danger"], foreground="white", borderwidth=0, font=('Segoe UI', 10, 'bold'))
        self.stil.map("Danger.TButton", background=[('active', self.RENKLER["danger_hover"])])
        self.stil.configure("Sidebar.TButton", background="#34495e", foreground="white", borderwidth=0, font=('Segoe UI', 10), anchor="w", padding=6)
        self.stil.map("Sidebar.TButton", background=[('active', self.RENKLER["primary"])])
        self.stil.configure("Treeview", background="white", fieldbackground="white", foreground=self.RENKLER["text_dark"], rowheight=30, borderwidth=0)
        self.stil.configure("Treeview.Heading", background=self.RENKLER["table_header"], foreground=self.RENKLER["text_dark"], font=('Segoe UI', 10, 'bold'), relief="flat")
        self.stil.map("Treeview", background=[('selected', self.RENKLER["primary"])], foreground=[('selected', 'white')])
        self.stil.configure("TNotebook", background=self.RENKLER["bg_ana"], borderwidth=0)
        self.stil.configure("TNotebook.Tab", background="#dfe6e9", foreground=self.RENKLER["text_dark"], padding=[20, 8], font=('Segoe UI', 10))
        self.stil.map("TNotebook.Tab", background=[('selected', "white")], foreground=[('selected', self.RENKLER["primary"])])

    def goster_bildirim(self, mesaj, tip='bilgi'):
        if hasattr(self, '_bildirim_id') and self._bildirim_id:
            self.master.after_cancel(self._bildirim_id)
        renk_map = {'bilgi': (self.RENKLER["primary"], "#d6eaf8"), 'uyarı': ('#d35400', '#fadbd8'), 'hata':  ('#c0392b', '#f2d7d5')}
        fg, bg = renk_map.get(tip, ('black', 'white'))
        self.lbl_bildirim.config(text=f"  {mesaj}  ", foreground=fg, background=bg)
        self.lbl_bildirim.pack(side='bottom', fill='x', ipady=10)
        self._bildirim_id = self.master.after(4000, self.lbl_bildirim.pack_forget)

    def _arayuz_olustur(self):
        main_frame = ttk.Frame(self.master)
        main_frame.pack(fill='both', expand=True)

        # SOL PANEL
        sol_panel_dis = ttk.Frame(main_frame, width=260, style="Sidebar.TFrame") 
        sol_panel_dis.pack(side='left', fill='y')
        
        sol_frame = ttk.Frame(sol_panel_dis, style="Sidebar.TFrame")
        sol_frame.pack(fill='both', expand=True, padx=15, pady=20)
        
        ttk.Label(sol_frame, text="ENVANTER PRO", style="SidebarHeader.TLabel").pack(pady=(0, 5), anchor='w')
        ttk.Label(sol_frame, text="Yönetim Paneli", style="Sidebar.TLabel", font=('Segoe UI', 9)).pack(pady=(0, 30), anchor='w')

        self.kritik_kart = ttk.LabelFrame(sol_frame, text="KRİTİK UYARI", padding=10, style="SidebarCard.TLabelframe")
        self.kritik_kart.pack(fill='x', pady=(0, 30))
        self.lbl_kritik = ttk.Label(self.kritik_kart, text="0 Ürün", font=('Segoe UI', 16, 'bold'), foreground="#e74c3c", background=self.RENKLER["bg_sidebar"])
        self.lbl_kritik.pack(anchor='center')

        ttk.Label(sol_frame, text="HIZLI İŞLEMLER", font=('Segoe UI', 9, 'bold'), foreground="#bdc3c7", background=self.RENKLER["bg_sidebar"]).pack(anchor='w', pady=(10, 5))
        ttk.Button(sol_frame, text="  📦  Yeni Malzeme Ekle", style='Sidebar.TButton', command=lambda: self.notebook.select(self.tab_index_map['Stok İşlemleri'])).pack(fill='x', pady=2)
        ttk.Button(sol_frame, text="  🔄  Stok Güncelle", style='Sidebar.TButton', command=lambda: self.notebook.select(self.tab_index_map['Stok İşlemleri'])).pack(fill='x', pady=2)
        
        tk.Frame(sol_frame, height=1, bg="#34495e").pack(fill='x', pady=15)
        
        ttk.Label(sol_frame, text="MODÜLLER", font=('Segoe UI', 9, 'bold'), foreground="#bdc3c7", background=self.RENKLER["bg_sidebar"]).pack(anchor='w', pady=(0, 5))
        ttk.Button(sol_frame, text="  📑  Reçete Yönetimi", style='Sidebar.TButton', command=lambda: self.notebook.select(self.tab_index_map['Reçete Yönetimi'])).pack(fill='x', pady=2)
        ttk.Button(sol_frame, text="  🛒  Sipariş İşle", style='Sidebar.TButton', command=lambda: self.notebook.select(self.tab_index_map['Sipariş İşle'])).pack(fill='x', pady=2)
        ttk.Button(sol_frame, text="  📜  İşlem Geçmişi", style='Sidebar.TButton', command=lambda: self.notebook.select(self.tab_index_map['İşlem Geçmişi'])).pack(fill='x', pady=2)

        ttk.Button(sol_frame, text="🗑️ Seçiliyi Sil", style='Danger.TButton', command=self.malzeme_kaldir_islemi).pack(fill='x', pady=20, side='bottom')

        # SAĞ PANEL
        sag_frame = ttk.Frame(main_frame)
        sag_frame.pack(side='right', fill='both', expand=True, padx=20, pady=20)

        header_frame = ttk.Frame(sag_frame)
        header_frame.pack(fill='x', pady=(0, 15))
        ttk.Label(header_frame, text="Stok Envanteri", font=('Segoe UI', 16, 'bold'), foreground="#2c3e50").pack(side='left')
        
        search_frame = ttk.Frame(header_frame)
        search_frame.pack(side='right')
        ttk.Label(search_frame, text="🔍", font=('Segoe UI', 12)).pack(side='left', padx=5)
        self.ent_arama = ttk.Entry(search_frame, width=25)
        self.ent_arama.pack(side='left', padx=5)
        self.ent_arama.bind('<KeyRelease>', self.arama_yap)
        ttk.Button(search_frame, text="Excel/CSV", style='Success.TButton', command=self.excel_aktar, width=12).pack(side='left', padx=5)

        tablo_container = ttk.Frame(sag_frame, style="Card.TFrame", padding=1) 
        tablo_container.pack(fill='x', pady=(0, 20), expand=False)
        self._malzeme_tablosu_olustur(tablo_container)

        self.notebook = ttk.Notebook(sag_frame)
        self.notebook.pack(fill='both', expand=True)

        self.tab_index_map = {}
        
        self.tab_stok_islemleri = tk.Frame(self.notebook, bg="white", padx=20, pady=20)
        self.notebook.add(self.tab_stok_islemleri, text="Stok İşlemleri")
        self._form_hizli_islem_olustur(self.tab_stok_islemleri)
        self.tab_index_map['Stok İşlemleri'] = 0
        
        self.tab_recete = tk.Frame(self.notebook, bg="white", padx=20, pady=20)
        self.notebook.add(self.tab_recete, text="Reçete Yönetimi")
        self._form_recete_yonetimi(self.tab_recete)
        self.tab_index_map['Reçete Yönetimi'] = 1
        
        self.tab_siparis = tk.Frame(self.notebook, bg="white", padx=20, pady=20)
        self.notebook.add(self.tab_siparis, text="Sipariş İşle")
        self._form_siparis_isle(self.tab_siparis)
        self.tab_index_map['Sipariş İşle'] = 2
        
        self.tab_gecmis = tk.Frame(self.notebook, bg="white", padx=20, pady=20)
        self.notebook.add(self.tab_gecmis, text="İşlem Geçmişi")
        self._gecmis_tablosu_olustur(self.tab_gecmis)
        self.tab_index_map['İşlem Geçmişi'] = 3
        
        self.lbl_bildirim = tk.Label(self.master, text="", font=('Segoe UI', 10, 'bold'), pady=0, borderwidth=0)

    # --- ALT BİLEŞENLER ---
    
    def _malzeme_tablosu_olustur(self, parent):
        cols = ('id', 'ad', 'miktar', 'kritik_esik')
        self.stok_tablosu = ttk.Treeview(parent, columns=cols, show='headings', selectmode='browse', height=8)
        sb = ttk.Scrollbar(parent, orient="vertical", command=self.stok_tablosu.yview)
        self.stok_tablosu.configure(yscrollcommand=sb.set)
        
        self.stok_tablosu.tag_configure('kritik', background='#fadbd8', foreground='#c0392b') 
        self.stok_tablosu.tag_configure('yaklasan', background='#fcf3cf', foreground='#d35400') 

        self.stok_tablosu.heading('id', text='ID', anchor='w')
        self.stok_tablosu.heading('ad', text='Malzeme Adı', anchor='w')
        self.stok_tablosu.heading('miktar', text='Miktar', anchor='e')
        self.stok_tablosu.heading('kritik_esik', text='Kritik Eşik', anchor='e')

        self.stok_tablosu.column('id', width=50, anchor='w', stretch=False)
        self.stok_tablosu.column('ad', width=350, anchor='w', stretch=True)
        self.stok_tablosu.column('miktar', width=120, anchor='e')
        self.stok_tablosu.column('kritik_esik', width=120, anchor='e')

        self.stok_tablosu.bind('<Double-1>', self.secili_malzeme_stok_guncelle_otomatik)
        
        self.stok_tablosu.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

    def _gecmis_tablosu_olustur(self, parent):
        cols = ('id', 'tarih', 'islem', 'aciklama', 'miktar')
        header_frame = tk.Frame(parent, bg="white")
        header_frame.pack(fill='x', pady=(0, 10))
        tk.Label(header_frame, text="Son İşlemler", font=('Segoe UI', 12, 'bold'), bg="white", fg="#2c3e50").pack(side='left')
        ttk.Button(header_frame, text="🗑️ Geçmişi Temizle", style='Danger.TButton', command=self._gecmisi_temizle_islemi).pack(side='right')
        
        self.trv_gecmis = ttk.Treeview(parent, columns=cols, show='headings', height=6)
        sb = ttk.Scrollbar(parent, orient="vertical", command=self.trv_gecmis.yview)
        self.trv_gecmis.configure(yscrollcommand=sb.set)

        self.trv_gecmis.heading('id', text='ID', anchor='w')
        self.trv_gecmis.heading('tarih', text='Tarih', anchor='w')
        self.trv_gecmis.heading('islem', text='İşlem Tipi', anchor='w')
        self.trv_gecmis.heading('aciklama', text='Açıklama', anchor='w')
        self.trv_gecmis.heading('miktar', text='Değişim', anchor='e')

        self.trv_gecmis.column('id', width=40, stretch=False)
        self.trv_gecmis.column('tarih', width=130)
        self.trv_gecmis.column('islem', width=120)
        self.trv_gecmis.column('aciklama', width=350, stretch=True)
        self.trv_gecmis.column('miktar', width=80, anchor='e')

        self.trv_gecmis.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

    def _form_recete_yonetimi(self, parent):
        left_frame = tk.Frame(parent, bg="white")
        left_frame.pack(side='left', fill='y', padx=(0, 25))
        
        tk.Label(left_frame, text="Tanımlı Ürünler (Reçeteler)", font=('Segoe UI', 10, 'bold'), bg="white", fg="#2c3e50").pack(anchor='w')
        
        self.urun_listesi_var = tk.StringVar()
        self.lst_urunler = tk.Listbox(left_frame, listvariable=self.urun_listesi_var, height=10, width=30, 
                                      bd=0, bg="#ecf0f1", highlightthickness=0, selectbackground=self.RENKLER["primary"], 
                                      selectforeground="white", font=('Segoe UI', 10))
        self.lst_urunler.pack(fill='both', expand=True, pady=5)
        self.lst_urunler.bind('<<ListboxSelect>>', lambda e: self.recete_detay_goster())

        btn_frame = tk.Frame(left_frame, bg="white")
        btn_frame.pack(fill='x', pady=5)
        ttk.Button(btn_frame, text="Yeni Ürün", width=10, style='Success.TButton', command=self.yeni_recete_dialog).pack(side='left', padx=1)
        ttk.Button(btn_frame, text="Sil", width=5, style='Danger.TButton', command=self.recete_sil).pack(side='right', padx=1)

        self.right_frame_recete = tk.Frame(parent, bg="white")
        self.right_frame_recete.pack(side='right', fill='both', expand=True)
        
        header_frame = tk.Frame(self.right_frame_recete, bg="white")
        header_frame.pack(fill='x', pady=(0, 10))
        self.lbl_recete_baslik = tk.Label(header_frame, text="Reçete Detayı (Seçim Yapınız)", font=('Segoe UI', 11, 'bold'), fg="#2c3e50", bg="white")
        self.lbl_recete_baslik.pack(side='left')
        
        cols = ('id', 'ad', 'miktar')
        self.trv_recete = ttk.Treeview(self.right_frame_recete, columns=cols, show='headings', height=4)
        self.trv_recete.heading('id', text='ID', anchor='w')
        self.trv_recete.heading('ad', text='Hammadde', anchor='w')
        self.trv_recete.heading('miktar', text='Birim Başına Gerekli', anchor='e')
        
        self.trv_recete.column('id', width=50, stretch=False)
        self.trv_recete.column('ad', width=200, stretch=True)
        self.trv_recete.column('miktar', width=100, anchor='e')
        self.trv_recete.pack(fill='both', expand=True)

        ctrl_frame = tk.Frame(self.right_frame_recete, bg="white", pady=10)
        ctrl_frame.pack(fill='x')
        ttk.Button(ctrl_frame, text="- Bileşen Çıkar", style='Danger.TButton', command=self.recete_bilesen_sil).pack(side='right')
        ttk.Button(ctrl_frame, text="+ Bileşen Ekle", style='Success.TButton', command=self.recete_bilesen_ekle_dialog).pack(side='right', padx=10)

    def _form_siparis_isle(self, parent):
        center_frame = tk.Frame(parent, bg="white")
        center_frame.pack(anchor='center', pady=30)
        tk.Label(center_frame, text="Üretilecek Ürün:", bg="white", font=('Segoe UI', 11)).grid(row=0, column=0, padx=10, sticky='e')
        self.cmb_siparis_urun = ttk.Combobox(center_frame, state="readonly", width=35)
        self.cmb_siparis_urun.grid(row=0, column=1, padx=10, ipady=3)
        tk.Label(center_frame, text="Sipariş Adedi:", bg="white", font=('Segoe UI', 11)).grid(row=1, column=0, padx=10, pady=15, sticky='e')
        self.ent_siparis_adet = ttk.Entry(center_frame, width=37)
        self.ent_siparis_adet.grid(row=1, column=1, padx=10, ipady=3)
        ttk.Button(center_frame, text="Üret ve Stoktan Düş", style='Primary.TButton', command=self.siparis_isle).grid(row=2, column=1, pady=20, sticky='e')

    def _form_hizli_islem_olustur(self, parent):
        form_container = ttk.Frame(parent, style="Card.TFrame")
        form_container.pack(fill='both', expand=True)

        # Ekle
        frm_ekle = ttk.LabelFrame(form_container, text="➕ YENİ MALZEME TANIMLA", padding=15, style="TLabelframe")
        frm_ekle.pack(side='left', padx=15, fill='y', expand=True)
        form_ekle = ttk.Frame(frm_ekle, style="Card.TFrame")
        form_ekle.pack(expand=True)
        ttk.Label(form_ekle, text="Adı:", style="Card.TLabel").grid(row=0, column=0, padx=10, pady=5, sticky='e')
        self.ent_ekle_ad = ttk.Entry(form_ekle, width=30)
        self.ent_ekle_ad.grid(row=0, column=1, padx=10, pady=5)
        ttk.Label(form_ekle, text="Başlangıç Miktarı:", style="Card.TLabel").grid(row=1, column=0, padx=10, pady=5, sticky='e')
        self.ent_ekle_miktar = ttk.Entry(form_ekle, width=15)
        self.ent_ekle_miktar.insert(0, "0")
        self.ent_ekle_miktar.grid(row=1, column=1, padx=10, pady=5, sticky='w')
        ttk.Label(form_ekle, text="Kritik Eşik:", style="Card.TLabel").grid(row=2, column=0, padx=10, pady=5, sticky='e')
        self.ent_ekle_esik = ttk.Entry(form_ekle, width=15)
        self.ent_ekle_esik.insert(0, "10")
        self.ent_ekle_esik.grid(row=2, column=1, padx=10, pady=5, sticky='w')
        ttk.Button(form_ekle, text="Malzemeyi Kaydet", style='Success.TButton', command=self._kaydet_malzeme).grid(row=3, column=0, columnspan=2, pady=10)

        # Güncelle
        frm_guncelle = ttk.LabelFrame(form_container, text="🔄 MEVCUT STOK GÜNCELLE", padding=15, style="TLabelframe")
        frm_guncelle.pack(side='left', padx=15, fill='y', expand=True)
        form_guncelle = ttk.Frame(frm_guncelle, style="Card.TFrame")
        form_guncelle.pack(expand=True)
        ttk.Label(form_guncelle, text="Malzeme Seçimi:", style="Card.TLabel").grid(row=0, column=0, padx=10, pady=5, sticky='e')
        self.cmb_guncelle_malzeme = ttk.Combobox(form_guncelle, state="readonly", width=30)
        self.cmb_guncelle_malzeme.grid(row=0, column=1, padx=10, pady=5)
        ttk.Label(form_guncelle, text="İşlem Miktarı:", style="Card.TLabel").grid(row=1, column=0, padx=10, pady=5, sticky='e')
        self.ent_guncelle_miktar = ttk.Entry(form_guncelle, width=15)
        self.ent_guncelle_miktar.grid(row=1, column=1, padx=10, pady=5, sticky='w')
        self.var_guncelle_islem = tk.StringVar(value="ekle")
        frm_radio = ttk.Frame(form_guncelle, style="Card.TFrame")
        frm_radio.grid(row=2, column=1, sticky='w', pady=5)
        tk.Radiobutton(frm_radio, text="Ekle (+)", variable=self.var_guncelle_islem, value="ekle", 
                       bg="white", activebackground="white", font=('Segoe UI', 10)).pack(side='left')
        tk.Radiobutton(frm_radio, text="Çıkar (-)", variable=self.var_guncelle_islem, value="cikar", 
                       bg="white", activebackground="white", font=('Segoe UI', 10)).pack(side='left', padx=10)
        ttk.Button(form_guncelle, text="Stok Güncelle", style='Primary.TButton', command=self._guncelle_stok).grid(row=3, column=0, columnspan=2, pady=10)

    # --- İŞ MANTIĞI ---

    def malzeme_tablosunu_doldur(self, filtre=""):
        for i in self.stok_tablosu.get_children():
            self.stok_tablosu.delete(i)
        
        self.cmb_guncelle_malzeme['values'] = []
        combo_values = []
        veriler = self.db.malzemeleri_oku()
        
        for mid, ad, miktar, esik in veriler:
            if filtre and filtre.lower() not in ad.lower():
                continue
            combo_values.append(f"{ad} (ID: {mid})")
            tags = []
            if miktar <= esik:
                tags.append('kritik')
            elif miktar <= esik * 1.5:
                tags.append('yaklasan')
            self.stok_tablosu.insert('', 'end', values=(mid, ad, f"{miktar:.2f}", esik), tags=tags)
        
        self.cmb_guncelle_malzeme['values'] = combo_values
        self.kritik_durumu_goster()

    def arama_yap(self, event=None):
        aranan = self.ent_arama.get()
        self.malzeme_tablosunu_doldur(aranan)

    def kritik_durumu_goster(self):
        sayi = self.db.kritik_sayisi_hesapla()
        self.lbl_kritik.config(text=f"{sayi} Ürün")
        if sayi > 0:
            self.lbl_kritik.config(foreground="#e74c3c")
        else:
            self.lbl_kritik.config(foreground="#2ecc71")

    def _kaydet_malzeme(self):
        ad = self.ent_ekle_ad.get().strip()
        try:
            mik = float(self.ent_ekle_miktar.get())
            esik = int(self.ent_ekle_esik.get())
            if not ad: raise ValueError
        except:
            self.goster_bildirim("Hatalı giriş!", "hata")
            return
        
        res = self.db.malzeme_ekle(ad, mik, esik)
        if res is True:
            self.goster_bildirim(f"'{ad}' başarıyla eklendi.", "bilgi")
            self.veri_yenile()
            self.ent_ekle_ad.delete(0, 'end')
            self.ent_ekle_miktar.delete(0, 'end')
            self.ent_ekle_miktar.insert(0, "0")
        else:
            self.goster_bildirim(res, "hata")

    def _guncelle_stok(self):
        val = self.cmb_guncelle_malzeme.get()
        if not val:
            self.goster_bildirim("Lütfen bir malzeme seçin.", "uyarı")
            return
        try:
            mid = int(val.split('(ID: ')[1].strip(')'))
            mik = float(self.ent_guncelle_miktar.get())
        except:
            self.goster_bildirim("Hatalı miktar girişi!", "hata")
            return
            
        degisim = mik if self.var_guncelle_islem.get() == "ekle" else -mik
        res = self.db.stok_guncelle(mid, degisim)
        if res is True:
            self.goster_bildirim("Stok güncellendi.", "bilgi")
            self.veri_yenile()
            self.ent_guncelle_miktar.delete(0, 'end')
        else:
            self.goster_bildirim(res, "hata")

    def secili_malzeme_stok_guncelle_otomatik(self, event):
        selected = self.stok_tablosu.selection()
        if not selected: return
        item = self.stok_tablosu.item(selected[0])
        val = item['values'] 
        self.notebook.select(self.tab_index_map['Stok İşlemleri'])
        hedef_str = f"{val[1]} (ID: {val[0]})"
        self.cmb_guncelle_malzeme.set(hedef_str)
        self.ent_guncelle_miktar.focus_set()

    def malzeme_kaldir_islemi(self):
        selected = self.stok_tablosu.selection()
        if not selected:
            messagebox.showwarning("Seçim Yok", "Lütfen silinecek bir malzeme seçin.")
            return
        item = self.stok_tablosu.item(selected[0])
        mid = item['values'][0]
        ad = item['values'][1]

        if messagebox.askyesno("Onay", f"'{ad}' adlı malzemeyi silmek istediğinize emin misiniz?"):
            res = self.db.malzeme_kaldir(mid)
            if res is True:
                self.goster_bildirim("Malzeme silindi.", "bilgi")
                self.veri_yenile()
            else:
                self.goster_bildirim(str(res), "hata")

    def recete_listesini_guncelle(self):
        tarifler = self.db.tarifleri_cek()
        self.lst_urunler.delete(0, 'end')
        self.cmb_siparis_urun['values'] = tarifler
        for t in tarifler:
            self.lst_urunler.insert('end', t)

    def recete_detay_goster(self):
        selection = self.lst_urunler.curselection()
        if not selection: return
        urun_adi = self.lst_urunler.get(selection[0])
        self.lbl_recete_baslik.config(text=f"Reçete: {urun_adi}")
        for i in self.trv_recete.get_children():
            self.trv_recete.delete(i)
        bilesenler = self.db.tarif_bilesenlerini_cek(urun_adi)
        for mid, ad, adet in bilesenler:
            self.trv_recete.insert('', 'end', values=(mid, ad, adet))

    def yeni_recete_dialog(self):
        yeni_ad = simpledialog.askstring("Yeni Ürün", "Oluşturulacak Reçete/Ürün Adı:")
        if yeni_ad:
            self.recete_bilesen_ekle_dialog(on_tanimli_isim=yeni_ad)

    def recete_bilesen_ekle_dialog(self, on_tanimli_isim=None):
        target_urun_adi = on_tanimli_isim
        if not target_urun_adi:
            selection = self.lst_urunler.curselection()
            if not selection:
                messagebox.showwarning("Uyarı", "Lütfen soldan bir ürün seçin veya Yeni Ürün oluşturun.")
                return
            target_urun_adi = self.lst_urunler.get(selection[0])
        malzemeler = self.db.malzemeleri_oku()
        if not malzemeler:
            messagebox.showerror("Hata", "Önce stoktan malzeme tanımlamalısınız.")
            return
        malzeme_dict = {f"{m[1]} (ID:{m[0]})": m[0] for m in malzemeler}
        top = tk.Toplevel(self.master)
        top.title(f"'{target_urun_adi}' İçin Bileşen Ekle")
        top.geometry("350x250")
        tk.Label(top, text="Kullanılacak Hammadde:").pack(pady=5)
        cmb = ttk.Combobox(top, values=list(malzeme_dict.keys()), state="readonly", width=30)
        cmb.pack(pady=5)
        tk.Label(top, text="Gerekli Miktar:").pack(pady=5)
        ent = ttk.Entry(top)
        ent.pack(pady=5)
        def ekle():
            secim = cmb.get()
            miktar_str = ent.get()
            if not secim or not miktar_str: return
            mid = malzeme_dict[secim]
            try:
                mik = float(miktar_str)
            except:
                messagebox.showerror("Hata", "Miktar sayı olmalıdır.")
                return
            res = self.db.tarif_bilesen_ekle(target_urun_adi, mid, mik)
            if res is True:
                top.destroy()
                self.recete_listesini_guncelle()
                items = self.lst_urunler.get(0, tk.END)
                if target_urun_adi in items:
                    idx = items.index(target_urun_adi)
                    self.lst_urunler.selection_clear(0, tk.END)
                    self.lst_urunler.selection_set(idx)
                    self.lst_urunler.event_generate("<<ListboxSelect>>")
                self.recete_detay_goster()
                self.goster_bildirim("Bileşen eklendi.", "bilgi")
            else:
                messagebox.showerror("Hata", str(res))
        ttk.Button(top, text="Listeye Ekle", command=ekle).pack(pady=15)

    def recete_bilesen_sil(self):
        selection = self.lst_urunler.curselection()
        item_sel = self.trv_recete.selection()
        if not selection or not item_sel: return
        urun_adi = self.lst_urunler.get(selection[0])
        mid = self.trv_recete.item(item_sel[0])['values'][0]
        self.db.recete_bileseni_kaldir(urun_adi, mid)
        self.recete_detay_goster()

    def recete_sil(self):
        selection = self.lst_urunler.curselection()
        if not selection: return
        urun_adi = self.lst_urunler.get(selection[0])
        if messagebox.askyesno("Onay", f"'{urun_adi}' reçetesini tamamen silmek istiyor musunuz?"):
            self.db.recete_sil(urun_adi)
            self.recete_listesini_guncelle()
            for i in self.trv_recete.get_children():
                self.trv_recete.delete(i)

    def siparis_isle(self):
        urun = self.cmb_siparis_urun.get()
        try:
            adet = float(self.ent_siparis_adet.get())
            if adet <= 0: raise ValueError
        except:
            self.goster_bildirim("Geçerli bir adet giriniz.", "hata")
            return
        if not urun:
            self.goster_bildirim("Ürün seçilmedi.", "uyarı")
            return
        if messagebox.askyesno("Onay", f"{adet} adet '{urun}' üretilecek ve stoktan düşülecek. Onaylıyor musunuz?"):
            res = self.db.siparis_isleme_ve_stok_dus(urun, adet)
            if res is True:
                messagebox.showinfo("Başarılı", "Üretim kaydı oluşturuldu, stoklar güncellendi.")
                self.ent_siparis_adet.delete(0, 'end')
                self.veri_yenile()
            else:
                messagebox.showerror("İşlem Başarısız", str(res))

    def gecmis_yenile(self):
        for i in self.trv_gecmis.get_children():
            self.trv_gecmis.delete(i)
        data = self.db.islem_gecmisi_oku()
        for row in data:
            self.trv_gecmis.insert('', 'end', values=row)

    def _gecmisi_temizle_islemi(self):
        if messagebox.askyesno("Dikkat", "Tüm işlem geçmişi silinecek."):
            res = self.db.gecmisi_temizle()
            if res is True:
                self.goster_bildirim("Geçmiş temizlendi.", "bilgi")
                self.gecmis_yenile()
            else:
                self.goster_bildirim(res, "hata")

    def excel_aktar(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Dosyası", "*.csv")])
        if not path: return
        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';') 
                writer.writerow(['ID', 'Malzeme Adı', 'Miktar', 'Kritik Eşik'])
                data = self.db.malzemeleri_oku()
                writer.writerows(data)
            messagebox.showinfo("Başarılı", "Dosya kaydedildi. Excel ile çift tıklayarak açabilirsiniz.")
        except Exception as e:
            messagebox.showerror("Hata", f"Dosya kaydedilemedi: {e}")

    def veri_yenile(self):
        self.malzeme_tablosunu_doldur()
        self.gecmis_yenile()
        self.recete_listesini_guncelle()

if __name__ == "__main__":
    root = tk.Tk()
    app = MalzemeTakipUygulamasi(root)
    root.mainloop()