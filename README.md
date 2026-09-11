# 100 Days of Code — Python (YouTube) + SmartConvertAI

Welcome! This repo contains **two live websites**:

### 🌐 1. 100 Days of Code Portal — http://localhost:3001
Modern, dark, glassmorphic portal for the entire course.

**Features:**
- 100 days grid with search (⌘K) and category filters
- Live code preview (main.py) + tutorial notes
- Progress tracking (localStorage), mark done, streak
- Copy / download code, syntax highlighted
- Responsive, Geist font, Tailwind, Prism.js

**Run:**
```bash
cd website
python3 -m http.server 3001
# or: npx serve . -l 3001
```

### 📄 2. SmartConvertAI Scanner — http://localhost:3000
Industrial Xerox-grade document scanner in browser.

- Auto border detection (OpenCV Canny → contours → approxPolyDP → warpPerspective)
- B&W Xerox Mode: CCITT Group4, 20-80KB/page
- Smart Color MRC: text mask + color layer
- Next.js 14 + Python engine + optional Prisma

**Run:**
```bash
cd smartconvert-ai
npm install
npm run engine:setup   # creates python-engine/.venv
npm run dev            # http://localhost:3000
```

---

### Course Structure
- **Basics (Day 1-15):** Intro, modules, variables, strings, conditionals, loops
- **Intermediate (16-40):** Functions, lists, tuples, sets, dicts, exceptions
- **Advanced (41-70):** OOP, decorators, getters/setters, inheritance, class/static methods, super, magic methods
- **Projects (71-90):** Time module, CLI utility, shutil, requests, generators, caching, regex
- **Mastery (91-100):** AsyncIO, Threading, Multiprocessing + Conclusion

Each day folder contains:
- `main.py` — runnable code
- `.tutorial/Tutorial.md` — notes
- `.tutorial/image.png` — diagrams
- `.tutorial/video.json` — YouTube link

### Quick Start (Both Sites)
```bash
# Terminal 1 - Scanner
cd smartconvert-ai && npm run dev

# Terminal 2 - 100 Days Portal
cd website && python3 -m http.server 3001
```

Open:
- Scanner: https://3000-xxx.e2b.app
- Portal: https://3001-xxx.e2b.app

---
Built with ❤️ — Dark mode, glassmorphism, modern DX.
