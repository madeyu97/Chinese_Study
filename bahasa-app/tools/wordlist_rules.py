"""
Hand-made rules for turning the raw OpenSubtitles Malay frequency list into
the app's word list (used by build_wordlist.py).

  MERGE       abbreviations and OCR errors -> the real word (counts merged)
  SPLIT       wrongly joined spellings -> separate words (counts to each)
  KEEP        real Malay words the dictionary sets don't list
  INDO        Indonesian forms -> the usual Malaysian form (kept, flagged)
  NOT_INDO    words that look Indonesian by frequency but are Malaysian too
  DROP        names, English, subtitle markup, credit lines, OCR junk
  KEEP_WHOLE  word + clitic look-alikes that are words in their own right
              (masalah is not masa + -lah), never folded into a base word
  FOLD_DROP   folded forms too garbled to keep

Every list was built by reviewing the top 8,000 raw ranks by hand.
"""

# Abbreviations / OCR errors -> canonical word (counts merged)
MERGE = {
    'yg': 'yang', 'dgn': 'dengan', 'utk': 'untuk', 'mrk': 'mereka', 'dlm': 'dalam',
    'tdk': 'tidak', 'jgn': 'jangan', 'kpd': 'kepada', 'dpt': 'dapat', 'org': 'orang',
    'tn': 'tuan', 'pn': 'puan', 'lni': 'ini', 'ltu': 'itu', 'ltulah': 'itulah',
    'lndia': 'india', 'iagi': 'lagi', 'boieh': 'boleh', 'poiis': 'polis', 'daiam': 'dalam',
    'adaiah': 'adalah', 'lanya': 'ianya', 'berkerja': 'bekerja', 'menganggu': 'mengganggu',
    'eletrik': 'elektrik', 'jawap': 'jawab', 'stesyen': 'stesen', 'tunjukan': 'tunjukkan',
    'okay': 'okey',
}

# Wrongly joined spellings -> separate words (counts added to each part)
SPLIT = {
    'disini': 'di sini', 'dimana': 'di mana', 'disana': 'di sana', 'kemana': 'ke mana',
    'kesini': 'ke sini', 'kesana': 'ke sana', 'diatas': 'di atas', 'kedalam': 'ke dalam',
    'dibelakang': 'di belakang', 'ditempat': 'di tempat', 'disitu': 'di situ',
    'diantara': 'di antara', 'didepan': 'di depan', 'disebelah': 'di sebelah',
    'kebelakang': 'ke belakang', 'kebawah': 'ke bawah', 'kerumah': 'ke rumah',
    'didunia': 'di dunia', 'dihadapan': 'di hadapan', 'kedepan': 'ke depan',
    'disekitar': 'di sekitar', 'disinilah': 'di sinilah', 'dimanakah': 'di manakah',
    'darimana': 'dari mana', 'kemanapun': 'ke mana pun', 'terimakasih': 'terima kasih',
    'ibubapa': 'ibu bapa', 'seorangpun': 'seorang pun', 'itupun': 'itu pun',
    'siapapun': 'siapa pun', 'apapun': 'apa pun', 'tengahari': 'tengah hari',
    'macamana': 'macam mana', 'macammana': 'macam mana', 'lagipula': 'lagi pula',
    'satupun': 'satu pun', 'manapun': 'mana pun', 'didalam': 'di dalam',
    'diluar': 'di luar', 'dibawah': 'di bawah', 'keatas': 'ke atas', 'keluarga': None,
}
SPLIT = {k: v for k, v in SPLIT.items() if v}

# Real Malay words not found in the dictionary sets (colloquial, inflected) -> keep
KEEP = set('''
tak jom jomlah kat je yah tau korang diorang taklah takde takda taknak takpe pulak jugak aje ader
kot kak nakkan bagitahu bagitau rindukan yakah risaukan sejujurnya terhebat ketepi tawarkan
perkenalkan bencikan kenakan terburuk kru cintai sukakan magik dipenjara kejutkan sambungkan
sebutkan diaktifkan digelar ditemukan seminit segelas secawan sebotol bazirkan jangkakan sahkan
permainkan kahwini marahkan beratus bukakan luahkan bacakan tertanya persembahkan motorsikal
rileks lepasi medik sehebat fasiliti perolehi tuangkan tumpaskan perbuat tahukan doakan seburuk
ditendang dikepung pemandian dihalang resepi mensasarkan penjejak seakan seolah sekurangnya
menyintai penggusti petarung perbaiki sarankan la hah ko ah iya
'''.split())

# Indonesian forms kept in the corpus but flagged; value = usual Malaysian form
INDO = {
 'bisa':'boleh','ayo':'ayuh / jom','ayolah':'ayuhlah / jom','mau':'mahu / nak','oke':'okey',
 'karena':'kerana','bilang':'kata / cakap','bahwa':'bahawa','mengerti':'faham',
 'menemukan':'menjumpai','menemukannya':'menjumpainya','pikir':'fikir','berpikir':'berfikir',
 'pikirkan':'fikirkan','pikiran':'fikiran','kupikir':'aku fikir','pria':'lelaki',
 'polisi':'polis','uang':'wang / duit','butuh':'perlu','butuhkan':'perlukan','mencoba':'mencuba',
 'coba':'cuba','cobalah':'cubalah','bagian':'bahagian','berarti':'bermakna',
 'artinya':'maksudnya / ertinya','kabar':'khabar','kabarmu':'khabar kau','menurutmu':'pada pendapat kau',
 'kapan':'bila','khawatir':'risau / bimbang','paham':'faham','kumohon':'tolonglah','kamar':'bilik',
 'bicarakan':'bincangkan','membicarakan':'membincangkan','menit':'minit','telepon':'telefon',
 'menelepon':'menelefon','rencana':'rancangan','bisakah':'bolehkah','putri':'puteri',
 'putriku':'puteriku','putra':'putera','omong':'cakap','dokter':'doktor',
 'permisi':'tumpang lalu / maaf','silahkan':'silakan','nona':'cik','tampaknya':'nampaknya',
 'melewati':'melalui','bercanda':'bergurau','ide':'idea','keren':'hebat / best',
 'dimulai':'dimulakan','memulai':'memulakan','perusahaan':'syarikat','berbeda':'berbeza',
 'kemarin':'semalam','informasi':'maklumat','membutuhkan':'memerlukan','kasus':'kes',
 'nyonya':'puan','pribadi':'peribadi','rahasia':'rahsia','inggris':'Inggeris',
 'bisnis':'perniagaan','brengsek':'(Indonesian slang)','nyaman':'selesa','kubilang':'aku kata',
 'kukira':'aku ingat / sangka','kecelakaan':'kemalangan','pohon':'pokok','kantor':'pejabat',
 'sih':'(Indonesian particle)','membangun':'membina','gak':'tak','nggak':'tak','nomor':'nombor',
 'gedung':'bangunan','sadar':'sedar','istirahat':'rehat','prajurit':'askar','istri':'isteri',
 'istriku':'isteriku','militer':'tentera','pacar':'teman lelaki / wanita','kelompok':'kumpulan',
 'pengacara':'peguam','lanjutkan':'teruskan','surga':'syurga','cocok':'sesuai','tentara':'tentera',
 'pangeran':'putera raja','hewan':'haiwan','sebagian':'sebahagian','kartu':'kad','toko':'kedai',
 'minggir':'ke tepi','tas':'beg','terkadang':'kadang-kadang','kode':'kod','obat':'ubat',
 'konyol':'bodoh / mengarut','pasien':'pesakit','sepatu':'kasut','jawaban':'jawapan',
 'ketemu':'jumpa','menyebalkan':'menjengkelkan','kue':'kuih','sobat':'kawan','duluan':'dulu',
 'lelucon':'jenaka','mulai':'mula','berhasil':'berjaya','besok':'esok','kesempatan':'peluang',
 'pertanyaan':'soalan','pesta':'parti','sulit':'susah / sukar','menikah':'berkahwin',
 'pernikahan':'perkahwinan','ruangan':'ruang / bilik','detik':'saat','khusus':'khas',
 'paman':'pak cik','enak':'sedap','mengirim':'menghantar','mengirimkan':'menghantar',
 'kirim':'hantar','kirimkan':'hantarkan','pemerintah':'kerajaan','tamu':'tetamu','kabur':'lari',
 'aturan':'peraturan','truk':'lori','jendela':'tingkap','lingkungan':'persekitaran',
 'atap':'bumbung','kok':'(Indonesian particle)','nih':'ni','tuh':'tu','aja':'je / sahaja',
 'apaan':'apa','lumayan':'boleh tahan','tanggal':'tarikh','tombol':'butang','berteman':'berkawan',
 'mengemudi':'memandu','berkelahi':'bergaduh','ledakan':'letupan','badai':'ribut',
 'persetan':'(Indonesian curse)','bajingan':'(Indonesian curse)','sialan':'sial',
 'astaga':'alamak / ya Allah','bibi':'mak cik','darurat':'kecemasan','kesepakatan':'perjanjian',
 'terjebak':'terperangkap','menempatkan':'meletakkan','sukses':'berjaya','dingin':'sejuk',
 'menyenangkan':'menyeronokkan','beruntung':'bertuah','terlihat':'kelihatan',
 'sepertinya':'nampaknya','terserah':'terpulang','menaruh':'meletakkan','taruh':'letak',
 'pengadilan':'mahkamah','memangnya':'memang','selanjutnya':'seterusnya','berikutnya':'seterusnya',
 'korban':'mangsa','berteriak':'menjerit','cerdas':'bijak / pandai','setan':'syaitan',
 'komandan':'komander','mengerjakan':'membuat','mengunjungi':'melawat','lolos':'terlepas',
 'kutukan':'sumpahan','dikenal':'dikenali','beres':'selesai','menatap':'merenung',
 'melukai':'mencederakan','perdamaian':'keamanan','romantis':'romantik','penyihir':'ahli sihir',
 'menghancurkan':'memusnahkan','agen':'ejen','pintar':'pandai','terluka':'cedera',
 'petugas':'pegawai','berangkat':'bertolak','terdengar':'kedengaran','ternyata':'rupanya',
 'desa':'kampung','memperbaiki':'membaiki','memperbaikinya':'membaikinya','tampan':'kacak',
 'gugup':'gementar','pembohong':'penipu','kekerasan':'keganasan','bingung':'keliru',
 'pendeta':'paderi','tolol':'bodoh','klien':'pelanggan','parkir':'letak kereta',
 'staf':'kakitangan','berkas':'fail','poin':'mata','curang':'tipu','telanjang':'bogel',
 'pantat':'punggung','boneka':'anak patung','memesan':'menempah','layanan':'perkhidmatan',
 'ukuran':'saiz','sarankan':'cadangkan','mengira':'ingat / sangka','kenyataannya':'sebenarnya',
 'padahal':'sedangkan','percakapan':'perbualan','panggung':'pentas','haus':'dahaga',
 'tampil':'muncul','merobek':'mengoyak','diundang':'dijemput','mengundang':'menjemput',
 'petarung':'pejuang','penasaran':'ingin tahu','bandara':'lapangan terbang','rusak':'rosak',
 'merusak':'merosakkan','lezat':'lazat / sedap','sehat':'sihat','persiapkan':'sediakan',
 'kacamata':'cermin mata','terhubung':'bersambung','menyadari':'menyedari','loker':'lokar',
 'rekaman':'rakaman','jembatan':'jambatan','sekedar':'sekadar','ksatria':'kesatria',
 'proyek':'projek','maukah':'mahukah','musik':'muzik','halo':'helo',
}
# Low Indonesian/Malay ratio but standard Malaysian Malay too -> never auto-flag
NOT_INDO = set('''bicara berbicara bung tampak mundur dapatkah temanmu kuharap kudengar kulihat
kulakukan kurasa memberitahumu tim harus saat kalian setelah kota catatan foto semacam
mencintaimu kemari tewas kuliah lainnya sebelumnya menginginkan mengurus ampun tiarap bersulang
santai anggur tambang murni tumbuh merubah mengingat berduka daftar merindukanmu lantai siang
kotoran pasar hamil menyewa dulunya tepatnya sepakat muak waspada adegan terpenting mengajarkan
pegangan terbatas bapak mengenakan iya hal apakah punya memiliki bahkan aneh soal benarkah
maksudku aman sang tiap'''.split())

# Names, English, subtitle markup, credit lines, OCR junk -> drop
DROP = set('''
are set am long was had gay hang sun top pop bad mood signal lot cop post spring sin final babe
ring ran dozen original ain jesus yesus kristus amen indian british champagne mayor gang derek
virginia adam paul roman alan santa jean ham oak auto tara grey sara jim bob tom sarah iris jin tim
carter kate mei yu ken mac lena ana prem pam lucas kang wong joon ding mara kara megan maya florida
las roma paris cia sub min tan gong kung ali delta joker pai misa musa pi pro medal lap rum helm dil
lam kabir dol wan jed jem karan tata baron bebe mika gita samir kashmir loki nana yong argus lau bon
erik mel gus feng jong halloween victoria klaus rang natal
font color subtitle subbers diterjemah diterjemahkan apos thea geeta cisco boyka sil starling dory
merlyn hinata suzuran savitar genji singham dumbledore raees saiya toretto falcone serizawa zaara
diggle huo katniss hagrid chappie peeta glades sheeni hokage boov nobita smurfette boruto nui
castiel metatron sifu gabbar vegeta jaikant remz lycan munni snart gru bratva grodd ghul hogwarts
voldemort galavan hershel dhani thorin maroni yehuda mohini haku orc ryuzaki shinobi tej harleen
daepyonim selene patchi gargamel shado wukong rishabh blu mirakuru hanabi tei gusteau thawne fateh
ryeong kohinoor bajirao abaddon emm geet koba crawly taha mohenjo gotya krrish madhi taani weasley
gorg ghantt virat kovar shikre kaali ker tamao chunin gantz smoak drover kaiju viraj beerus
vedhalam maseo leito gryffindor shishio kabali khar dauntless braga babita sarman rone duraisingam
yorla mardon tevye bauji slytherin muggle malfoy altaaf rache bajrangi faza saruman mastani
godrivecrazily corben deckard apiq nn bm msc fb gcpd scpd tokio jogja mesias
'''.split())

INDO.update({'mobil':'kereta','ditemukan':'dijumpai'})
INDO.update({'ngga':'tak','udah':'dah / sudah'})
MERGE.update({'pertunjukkan':'pertunjukan'})
SPLIT.update({'dirumah':'di rumah','disebalik':'di sebalik','samada':'sama ada','harijadi':'hari jadi','semulajadi':'semula jadi'})
DROP |= {'mohd','sarikata','bond','sakura'}

KEEP_WHOLE = set('''
adalah masalah sekolah walaupun langkah tetamu sebenarnya akhirnya nampaknya rasanya baiklah
entahlah sudahlah meskipun lagipun bagaimanapun sekiranya setidaknya sepenuhnya sebaiknya
sebaliknya selebihnya biasanya rupanya agaknya katanya tentunya pastinya kelihatannya harusnya
terutamanya selalunya khususnya misalnya contohnya hakikatnya kenyataannya asalnya mulanya
awalnya dasarnya asasnya sebelumnya selamanya berikutnya kemudiannya dulunya tadinya andainya
secukupnya secepatnya menikah majalah risalah pesalah bermasalah selangkah sepatah bangku
makanya ertinya maknanya maksudnya sebabnya adakah apatah mahupun ataupun sekalipun tuanku
keduanya kesudahannya akibatnya hasilnya intinya seharusnya sepatutnya sesungguhnya
'''.split())
FOLD_DROP = {"banku", "didalamnya"}
CLITICS = ("nyalah", "nyakah", "nyapun", "nya", "kulah", "mulah", "ku", "mu", "lah", "kah",
           "pun", "tah")
PROCLITICS = ("kau", "ku")

INDO.update({
    'meledak': 'meletup', 'meski': 'walaupun', 'persis': 'betul-betul sama', 'jelek': 'hodoh',
    'kendali': 'kawalan', 'kursi': 'kerusi', 'biaya': 'kos / belanja', 'kakek': 'datuk / atuk',
    'kecepatan': 'kelajuan', 'kondisi': 'keadaan', 'kontak': 'hubungan', 'mantan': 'bekas',
    'olahraga': 'sukan', 'siswa': 'pelajar', 'jaksa': 'pendakwa raya',
    'setidaknya': 'sekurang-kurangnya', 'harusnya': 'sepatutnya', 'apalagi': 'apatah lagi',
    'bikin': 'buat', 'kelinci': 'arnab', 'paket': 'pakej',
})
# Everyday Indonesian speech the model writers leak (Phase 6 role-play).
INDO.update({'banget': 'sangat', 'dikit': 'sikit', 'gimana': 'macam mana', 'enggak': 'tak',
             'ngapain': 'buat apa'})
# Shared with Malaysian usage; not tagged.
NOT_INDO |= {'mil', 'berbagai', 'kelihatannya'}
