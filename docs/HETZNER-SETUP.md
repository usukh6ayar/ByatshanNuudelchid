# Hetzner дээр байршуулах — алхам алхмаар

`docs/DEPLOYMENT.md` бол журам. Энэ бол **эхний удаа** дагаж хийх заавар.

Хугацаа: сервер, домэйн бэлэн бол ойролцоогоор **2 цаг**. Үүний ихэнх нь
DNS тархах хүлээлт.

**Vercel биш.** Асуусан тул шалгасан — §549 PDF-ийг хүсэлтээс гадна
ажилтнаар үүсгэхийг шаарддаг, serverless-д тогтмол процесс байхгүй.
WeasyPrint `libcairo`/`libpango`, MIME шалгалт `libmagic` шаарддаг, аль нь ч
managed Python runtime дээр суухгүй. Дэлгэрэнгүй `ROADMAP.md:349`.

---

## 0. Юу худалдаж авах вэ

**Бүх дансыг захиалагчийн нэр дээр үүсгэнэ.** RFP §781 — сервер, домэйн,
өгөгдлийн сан, cloud storage-ийн эзэмшигч нь захиалагч. Хүлээлгэн өгөх нь
нэвтрэх мэдээлэл дамжуулах ажил байх ёстой, нүүлгэх ажил биш.

| Юу | Хаана | Үнэ | Тайлбар |
|---|---|---|---|
| Сервер | Hetzner Cloud, **CPX21**, **Singapore** | ~€12–15/сар | 3 vCPU / 4 GB. Улаанбаатараас 93 мс |
| Домэйн | iTools | жилээр | Зөвхөн домэйн, hosting биш |
| Object storage | Cloudflare R2 | $0.015/GB, гаралт үнэгүй | Зураг эцэг эх рүү урсдаг тул гаралт чухал |

Singapore сонгосон шалтгаан хэмжсэн: Улаанбаатараас Hetzner Singapore 93 мс,
Герман 121–128 мс (D3).

---

## 1. Hetzner сервер үүсгэх

1. https://console.hetzner.cloud → **захиалагчийн и-мэйлээр** бүртгүүлэх
2. **New Project** → нэр өгөх
3. **Add Server**:
   - Location: **Singapore**
   - Image: **Ubuntu 24.04**
   - Type: **CPX21** (3 vCPU / 4 GB / 80 GB)
   - SSH key: өөрийн нийтийн түлхүүрээ нэмэх (нууц үг биш — түлхүүр)
4. **Create & Buy now**

Сервер үүсэхэд **IP хаяг** гарч ирнэ. Үүнийг тэмдэглэ — бүх зүйл үүнээс
эхэлнэ. Жишээ: `5.223.41.7`

SSH түлхүүр байхгүй бол өөрийн компьютер дээр:

```bash
ssh-keygen -t ed25519 -C "kinder-deploy"
cat ~/.ssh/id_ed25519.pub    # энэ мөрийг Hetzner-т буулгана
```

---

## 2. DNS — энэ нь серверээс **өмнө** байх ёстой

Caddy гэрчилгээгээ өөрөө авдаг, 80 порт дээр. Нэр хараахан хаяг руу
заагаагүй бол баталгаажуулах юмгүй тул хүсэлт унана.

iTools-ийн удирдлагын хуудсанд:

| Төрөл | Нэр | Утга |
|---|---|---|
| A | `@` | серверийн IP (жишээ `5.223.41.7`) |

**Cloudflare proxy асаахгүй.** Cloudflare данс R2-ын улмаас байгаа ч DNS-ийг
тийш зөөх шаардлагагүй. Улбар шар үүл асаавал Cloudflare TLS-ийг өөр дээрээ
тасалж, Caddy 80 порт дээр эзэмшлээ батлаж чадахгүй болно.

Тархсан эсэхийг **өөр сүлжээнээс** шалга:

```bash
dig +short tanai-domain.mn
```

Серверийн IP буцаах хүртэл цааш явахгүй. Ихэвчлэн 5–30 минут, заримдаа
хэдэн цаг.

---

## 3. Серверийг бэлдэх

```bash
ssh root@СЕРВЕРИЙН_IP
```

### 3.1 Систем шинэчлэх, Docker суулгах

```bash
apt update && apt upgrade -y

# Docker — албан ёсны эх сурвалжаас
curl -fsSL https://get.docker.com | sh

docker --version
docker compose version
```

### 3.2 Галт хана

```bash
apt install -y ufw
ufw allow 22/tcp     # SSH — үүнийг мартвал өөрийгөө түгжинэ
ufw allow 80/tcp     # гэрчилгээ авах, шинэчлэхэд ЗААВАЛ хэрэгтэй
ufw allow 443/tcp    # HTTPS
ufw --force enable
ufw status
```

**80 портыг хаахгүй.** Let's Encrypt гэрчилгээг тэндүүр олгож, 60 хоног
тутам шинэчилдэг.

### 3.3 Автомат аюулгүй байдлын шинэчлэлт

```bash
apt install -y unattended-upgrades
dpkg-reconfigure --priority=low unattended-upgrades
```

---

## 4. Кодыг татах

```bash
mkdir -p /srv && cd /srv
git clone https://github.com/usukh6ayar/ByatshanNuudelchid.git kinder
cd kinder
```

Хувийн repo бол deploy key хэрэгтэй:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/deploy -N ""
cat ~/.ssh/deploy.pub
# → GitHub → repo → Settings → Deploy keys → Add (read-only хангалттай)
```

---

## 5. Cloudflare R2 (зургийн сан)

1. https://dash.cloudflare.com → **R2** → **Create bucket**
   - Нэр: `kinder-media`
   - **Public access: OFF** ← энэ мөр бүх зүйлээс чухал
2. **Manage R2 API Tokens** → **Create token**
   - Permission: **Object Read & Write**
   - Тухайн bucket-д хязгаарлах
3. Гарч ирэх `Access Key ID`, `Secret Access Key`, `Account ID`-г хадгал

**Bucket заавал хаалттай.** RFP §4.4, §21.10 — хүүхдийн зураг зөвхөн
холбоосоор хүрч болохгүй. Систем эрхийг шалгасны дараа богино хугацааны
гарын үсэгтэй холбоос өгдөг, энэ нь bucket нэрээ нууж байж л утга учиртай.
Нээлттэй bucket бол код юу ч хийсэн хүлээн авалт унана.

---

## 6. `.env` бөглөх

```bash
cd /srv/kinder
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(64))"   # түлхүүр үүсгэх
nano .env
```

Заавал өөрчлөх мөрүүд:

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=<дээрх тушаалын гаралт>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=tanai-domain.mn
DJANGO_CSRF_TRUSTED_ORIGINS=https://tanai-domain.mn
DOMAIN=tanai-domain.mn

POSTGRES_USER=kinder
POSTGRES_PASSWORD=<урт санамсаргүй нууц үг>
POSTGRES_DB=kinder
DATABASE_URL=postgres://kinder:<ЯГ ТЭР НУУЦ ҮГ>@db:5432/kinder

AWS_ACCESS_KEY_ID=<R2-ийн түлхүүр>
AWS_SECRET_ACCESS_KEY=<R2-ийн нууц түлхүүр>
AWS_STORAGE_BUCKET_NAME=kinder-media
AWS_S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
AWS_S3_REGION_NAME=auto
MEDIA_REDIRECT_SIGNED_URL=true
```

`POSTGRES_PASSWORD` ба `DATABASE_URL` доторх нууц үг **яг ижил** байх ёстой.
Эхнийх нь сан үүсгэхэд, хоёр дахь нь холбогдоход хэрэглэгддэг.

---

## 7. Байршуулах

```bash
./scripts/deploy.sh
```

Скрипт **таамаглахын оронд татгалздаг**. Дараах зургаагийн аль нэг буруу бол
тодорхой өгүүлбэрээр зогсоно:

| Татгалзал | Юу болох байсан |
|---|---|
| `DJANGO_SETTINGS_MODULE` буруу | Production дээр `DEBUG` асаалттай |
| `DJANGO_SECRET_KEY` хэвээр | Session, CSRF хуурамчаар үүсгэх боломжтой |
| `DOMAIN` хоосон | Caddy гэрчилгээ хүсэх боломжгүй |
| `POSTGRES_PASSWORD` хоосон | Сан нууц үггүй эхэлнэ |
| `AWS_STORAGE_BUCKET_NAME` хоосон | Сайт босч, зураг оруулах үед унана |
| `ALLOWED_HOSTS` / `CSRF` домэйнгүй | Бүх хүсэлт эсвэл бүх маягт унана |

Скрипт юу хийдэг: сан нөөцлөх → образ барих → `check --deploy` →
migration → статик файл → бүх контейнер эхлүүлэх → `/healthz` хариулахыг
хүлээх.

Эхний ажиллуулалт 5–10 минут (образ барих). Caddy гэрчилгээгээ 30 секундэд
авна.

### Эхний хэрэглэгч

```bash
docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser
```

**`seed_demo`-г production дээр битгий ажиллуул.** `DEBUG` унтраалттай үед
татгалздаг (§707), гэхдээ үүнд найдаж болохгүй.

---

## 8. Шалгах

```bash
curl https://tanai-domain.mn/healthz
# {"status": "ok", "checks": {"database": "ok", "cache": "ok"}}

docker compose -f docker-compose.prod.yml ps
```

**Таван контейнер + Caddy** ажиллаж байх ёстой:

| Процесс | Байхгүй бол |
|---|---|
| web | Сайт байхгүй |
| **worker** | PDF үүрд дараалалд үлдэнэ |
| **beat** | Хяналтын самбарын тоо шинэчлэгдэхгүй |
| postgres | Өгөгдөл байхгүй |
| redis | Кэш, дараалал байхгүй |

`worker` болон `beat` **сонголт биш**. Зөвхөн `web`-тэй суулгац эрүүл
харагдана, бүх хуудас нээгдэнэ, гэхдээ PDF хэзээ ч бэлэн болохгүй.

Дараа нь хөтчөөр орж:
- Нэвтрэх ажиллаж байна уу
- Хүүхэд бүртгээд зураг оруулах — R2 руу орж байгаа эсэх
- PDF үүсгэх — 30 секундэд бэлэн болох ёстой

---

## 9. Нөөцлөлт — эхний өдөртөө тохируулна

```bash
crontab -e
```

```cron
0 2 * * *  cd /srv/kinder && BACKUP_DIR=/srv/backups RETENTION_DAYS=30 ./scripts/backup.sh
```

**Архивуудыг серверээс гадагш хуулна.** Өгөгдлийн сантай нэг дискэн дээрх
нөөц нь нөөц хэрэгтэй болох аливаа зүйлээс амьд гарахгүй.

Сэргээхийг **хэрэгтэй болохоос өмнө** дадлагажуул — `README.md`-д
`TARGET_DB` ашиглан түр сан руу сэргээх журам бий.

---

## 10. Шинэчлэх

```bash
cd /srv/kinder
git pull
./scripts/deploy.sh
```

Ижил скрипт. Кодыг солихоос өмнө өөрөө нөөцөлдөг.

---

## 11. Сар бүрийн ажил

VPS бол түрээслэсэн үйлчилгээ биш, өөрийн эзэмшил. **Сард 1–2 цаг**:

- Хостын аюулгүй байдлын шинэчлэлт (`unattended-upgrades` ихэнхийг хийнэ)
- Docker болон үндсэн образын шинэчлэлт
- Дискний зай — PDF хугацаа дуусахад устдаг ч лог, хуучин образ хуримтлагдана
- **Нөөцлөлт үнэхээр ажилласан эсэхийг шалгах** — хамгийн их алгасагддаг,
  хамгийн чухал нь
- Сайт унасныг анзаарах хүн байх

Гаднаас `/healthz` рүү uptime хяналт тавь. Өөрийгөө хянадаг сервер нь
өөрөө унасан үедээ юу ч мэдээлэхгүй.

---

## 12. Энд хамрагдаагүй нэг эрсдэл

**Монголын хууль хүүхдийн мэдээллийг гадаадад хадгалахыг зөвшөөрөх эсэх нь
тогтоогдоогүй.** 2021 оны хувийн мэдээлэл хамгаалах хууль энэ талаар юу
хэлдгийг хуульчаас 5 минут асуух нь зүйтэй — эхний жинхэнэ гэр бүл орохоос
өмнө.

Хэрэв зөвшөөрөхгүй бол хариулт нь Монголын дата төв болно. Бүх зүйл Docker
дотор тул нүүлгэх нь энэ бичиг баримтыг дахин дагах ажил, өөр юу ч биш.
