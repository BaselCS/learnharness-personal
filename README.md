# LearnHarness Personal Learning Framework
# إطار التعلم الشخصي لـ LearnHarness

مستودع شخصي مستقل يدمج ثلاثة أطر تعليمية متكاملة في تجربة التعلم الشخصية على **LearnHarness**:

1. **تعليم الكبار (Andragogy)** — مبادئ مالكولم نولز الستة.
2. **المبادئ العشرة للعلوم** — الإطار التوجيهي التراثي لفهم العلوم وتمايزها.
3. **التعلم الفائق (Ultralearning)** — منهجية سكوت يونغ للتعلم المركز والفعال.

---

## المبادئ المعمارية الحاكمة (Architectural Guarantees)

1. **استقلال تام عن كود LearnHarness:**
   - لا تعديل لأي ملف داخل مستودع التطبيق الأساسي (`src/`, `components/`, `app/`, إلخ).
   - لا مساس بنظام التعريب (i18n) أو ملفات اللغات (`locales`).
   - لا تعديل على مخطط الرسم البياني المعرفي (Knowledge Graph schema) أو محرك التقييم أو أدوات Anki أو دورة المحادثة (turn pipeline).
2. **الاعتماد على منافذ التخصيص الرسمية:**
   - يستفيد الإطار من آلية التجاوز المدمجة في LearnHarness: دليل التجاوزات `data/prompts` والمفاتيح البرمجية `agent.prompts` في `data/settings.json`.
3. **النجاة من التحديثات (Update-Proof):**
   - لا يحتاج المستخدم إلى عمل Fork دائم لـ LearnHarness.
   - عند تحديث LearnHarness عبر `git pull`، يُعاد توليد ملفات التجاوز تلقائياً عبر دمج أحدث أجزاء الأوامر البرمجية من المنبع مع الملاحق الشخصية (Appendices).

---

## المتطلبات (Prerequisites)

- Python 3.10+ (يُفضل استخدام `uv`).
- Node.js و npm/pnpm لتشغيل اختبارات التركيب البرمجي (`prompt-composition.test.ts`).

---

## الاستخدام السريع (Quick Start)

### 1. تطبيق الإطار (Apply)
لتوليد ملفات التجاوز في `data/prompts` وتفعيلها في `settings.json`:
```bash
# استخدام uv أو python مباشرة:
uv run python scripts/apply.py

# أو بالإنجليزية إذا أردت:
uv run python scripts/apply.py --language en
```

### 2. التحقق من سلامة التثبيت (Verify)
للتأكد من مطابقة التجزئات وتفعيل المفاتيح وسلامة كود المنبع:
```bash
uv run python scripts/verify.py --strict
```

### 3. تشغيل الاختبارات القطعية (Test)
```bash
bash tests/run-composition-test.sh
# أو:
npm test
```

### 4. إزالة الإطار واستعادة الإعدادات الأصلية (Remove)
```bash
uv run python scripts/remove.py
```

---

## سير عمل التحديث (Updating LearnHarness)

عند وصول تحديثات جديدة من المستودع الأصلي:

```bash
# 1. تحديث مستودع LearnHarness
cd /home/basel/Work/LearnHarness
git pull upstream main

# 2. إعادة تطبيق الإطار الشخصي لدمج التحديثات مع الملاحق
cd /home/basel/Work/learnharness-personal
uv run python scripts/apply.py

# 3. التحقق من الصحة
uv run python scripts/verify.py --strict
```

---

## النسخ الاحتياطي على GitHub (Backup Workflow)

```bash
cd /home/basel/Work/learnharness-personal
git remote add origin git@github.com:<YOUR_USERNAME>/learnharness-personal.git
git branch -M main
git push -u origin main
```

---

## استعادة الإطار بعد إعادة التثبيت (Restoration Workflow)

إذا قمت بتثبيت LearnHarness من الصفر أو انتقلت لجهاز جديد:

```bash
# 1. استنساخ LearnHarness
git clone <learnharness-repo-url> ~/Work/LearnHarness
cd ~/Work/LearnHarness
npm install

# 2. استنساخ مستودعك الشخصي
git clone git@github.com:<YOUR_USERNAME>/learnharness-personal.git ~/Work/learnharness-personal
cd ~/Work/learnharness-personal

# 3. تطبيق الإطار فوراً
uv run python scripts/apply.py
uv run python scripts/verify.py --strict
```
