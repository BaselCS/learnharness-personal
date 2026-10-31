/**
 * Deterministic composition test for the personal LearnHarness customization.
 *
 * It does NOT call a model and makes no learning-outcome claim. It proves:
 *   1. the four supported override files are present, managed, and switched on;
 *   2. composeInstructions() actually composes the override instead of the source;
 *   3. the personal appendix text reaches only the intended agents;
 *   4. the nine-principle material stays in the teacher, not in prober/practice;
 *   5. the retention-after-understanding rule is present;
 *   6. utility agents and unmanaged prompt paths are not touched.
 *
 * Run from the LearnHarness checkout (so tsx and node_modules resolve):
 *   cd /home/basel/Work/LearnHarness
 *   LH_DATA_DIR=/home/basel/Work/LearnHarness/data \
 *     npx tsx --test /home/basel/Work/learnharness-personal/tests/prompt-composition.test.ts
 */

import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, it } from "node:test";

const REPO = process.env.LEARNHARNESS_REPO ?? path.join(os.homedir(), "Work", "LearnHarness");
const DATA = process.env.LH_DATA_DIR ?? path.join(REPO, "data");
const PERSONAL = path.resolve(import.meta.dirname, "..");

process.env.LH_DATA_DIR = DATA;

const { composeInstructions } = await import(path.join(REPO, "src/agent/teacher-agent.ts"));
const { effectivePromptSegments: effective } = await import(
	path.join(REPO, "src/agent/prompt-segments.ts")
);

const settings = JSON.parse(fs.readFileSync(path.join(DATA, "settings.json"), "utf-8")) as {
	general?: { language?: string };
	agent?: { prompts?: Record<string, boolean> };
};
const switches = settings.agent?.prompts ?? {};
const language = (settings.general?.language === "en" ? "en" : "ar") as "ar" | "en";

const manifest = JSON.parse(fs.readFileSync(path.join(PERSONAL, "manifest.json"), "utf-8")) as {
	segments: Array<{ path: string; appendix: string; agents: string[] }>;
};
const managedPaths = new Set(manifest.segments.map((s) => s.path));

const state = JSON.parse(
	fs.readFileSync(path.join(DATA, ".learnharness-personal.json"), "utf-8"),
) as { language?: string };
const installLanguage = (state.language === "en" ? "en" : "ar") as "ar" | "en";

const APPENDIX_MARKERS = {
	ar: {
		shared: "إطار التعلم الشخصي — عقيدة مشتركة بين الوكلاء",
		teacher: "إضافة شخصية — توجيه الموضوع والتخطيط للنقل",
		nine: "الفئات التسع:",
		prober: "إضافة شخصية — التحقيق مع المتعلم البالغ",
		practice: "إضافة شخصية — التدريب كمتعلم بالغ",
		unknown: "غير معروف",
		notApplicable: "لا ينطبق",
		requiresVerification: "يحتاج إلى تحقق",
		noFounder: "لا تختلق مؤسسًا",
		noStage: "لا تضف مرحلة جديدة",
		retention: "الاحتفاظ يبقى بعد الفهم",
		anki: "لا تنشئ بطاقات Anki",
		metalearning: "التعلم حول التعلم",
	},
	en: {
		shared: "Personal learning framework — cross-agent doctrine",
		teacher: "Personal addition — orienting the subject and planning for transfer",
		nine: "The nine categories:",
		prober: "Personal addition — probing the adult learner",
		practice: "Personal addition — practice as an adult, with deliberate training",
		unknown: "Unknown",
		notApplicable: "Not Applicable",
		requiresVerification: "Requires Verification",
		noFounder: "do not invent a single founder",
		noStage: "Do not add a new stage",
		retention: "Retention stays downstream of understanding",
		anki: "Do not create Anki cards",
		metalearning: "Metalearning",
	},
} as const;
const MARK = APPENDIX_MARKERS[installLanguage];

function composed(kind: "prober" | "teacher" | "practice", lang: "ar" | "en" = language): string {
	// The switches must be passed: composeInstructions(kind, undefined, lang)
	// deliberately bypasses overrides and returns pure source.
	return composeInstructions(kind, switches, lang);
}

function overrideOf(kind: "prober" | "teacher" | "practice", segment: string) {
	const found = effective(kind, switches, language).find((s) => s.path === segment);
	assert.ok(found, `${kind}: segment ${segment} not discovered`);
	return found;
}

describe("personal prompt overrides — installation", () => {
	it("has the four manifest segments enabled and composable", () => {
		assert.equal(manifest.segments.length, 4);
		for (const segment of manifest.segments) {
			assert.equal(switches[segment.path], true, `${segment.path} switch must be true`);
			const file = path.join(DATA, "prompts", ...segment.path.split("/"));
			assert.ok(fs.existsSync(file), `override file missing: ${file}`);
			const text = fs.readFileSync(file, "utf-8");
			assert.match(text, /^<!-- learnharness-personal: generated file/);
			assert.ok(text.includes("source-sha256:"), "header must record the source hash");
			assert.ok(text.includes(segment.appendix.split("/").pop()!), "appendix marker present");
		}
	});

	it("writes no override outside the manifest", () => {
		const promptsRoot = path.join(DATA, "prompts");
		const walk = (rel: string): string[] => {
			const dir = path.join(promptsRoot, rel);
			if (!fs.existsSync(dir)) return [];
			const out: string[] = [];
			for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
				const child = rel ? `${rel}/${entry.name}` : entry.name;
				if (entry.isDirectory()) out.push(...walk(child));
				else out.push(child);
			}
			return out;
		};
		for (const file of walk("")) {
			assert.ok(managedPaths.has(file), `unexpected unmanaged override: ${file}`);
		}
	});

	it("leaves utility agents and non-agent paths unmanaged", () => {
		for (const segment of manifest.segments) {
			const [first] = segment.path.split("/");
			assert.ok(["shared", "prober", "teacher", "practice"].includes(first), first);
		}
		const promptDirs = fs.readdirSync(path.join(REPO, "src/agent/prompts"), { withFileTypes: true });
		const agentDirs = promptDirs.filter((d) => d.isDirectory() && d.name !== "locales").map((d) => d.name);
		assert.ok(agentDirs.includes("prober") && agentDirs.includes("teacher") && agentDirs.includes("practice"));
		// Utility agents (research, pdf, visualization) do not live in this prompt tree
		// and receive none of these instructions.
		for (const name of ["research", "pdf", "visualization"]) {
			assert.ok(!agentDirs.includes(name), `unexpected prompt dir for utility agent: ${name}`);
		}
	});
});

describe("personal prompt overrides — composition", () => {
	it("teacher composes the personal appendix in both app languages", () => {
		for (const lang of ["ar", "en"] as const) {
			const text = composed("teacher", lang);
			assert.ok(text.includes(MARK.teacher), "teacher appendix present");
			assert.ok(text.includes(MARK.nine), "nine-principle orientation present");
			assert.ok(text.includes(MARK.unknown), "unknown marker present");
			assert.ok(text.includes(MARK.notApplicable), "not-applicable marker present");
			assert.ok(text.includes(MARK.requiresVerification), "verification marker present");
			assert.ok(text.includes(MARK.noFounder), "founder non-fabrication rule present");
			assert.ok(text.includes(MARK.noStage), "no-new-stage rule present");
			// The upstream planning source is preserved, not replaced.
			assert.ok(text.includes("## Planning — think hard here"), "source planning content retained");
		}
	});

	it("teacher receives nine principles exactly once (no duplication in shared/prober/practice)", () => {
		const teacher = composed("teacher");
		const prober = composed("prober");
		const practice = composed("practice");
		assert.equal((teacher.match(new RegExp(MARK.nine, "g")) ?? []).length, 1);
		assert.ok(!prober.includes(MARK.nine), "prober must not receive the nine principles");
		assert.ok(!practice.includes(MARK.nine), "practice must not receive the nine principles");
	});

	it("contains no operational reference to religious rulings or حكم الشارع", () => {
		for (const kind of ["prober", "teacher", "practice"] as const) {
			for (const lang of ["ar", "en"] as const) {
				const text = composed(kind, lang);
				assert.ok(!text.includes("حكم الشارع"), `${kind} ${lang} must not contain حكم الشارع`);
				assert.ok(!text.includes("حكم شرعي"), `${kind} ${lang} must not contain حكم شرعي`);
				assert.ok(!text.toLowerCase().includes("hukm"), `${kind} ${lang} must not contain hukm`);
				assert.ok(!text.toLowerCase().includes("religious ruling"), `${kind} ${lang} must not contain religious ruling`);
			}
		}
	});

	it("prober composes the adult probe appendix and shared doctrine", () => {
		for (const lang of ["ar", "en"] as const) {
			const text = composed("prober", lang);
			assert.ok(text.includes(MARK.prober), "prober appendix present");
			assert.ok(text.includes(MARK.shared), "shared doctrine present");
			assert.ok(text.includes(MARK.metalearning), "metalearning guidance present");
		}
	});

	it("practice composes the practice appendix and the shared accuracy doctrine", () => {
		for (const lang of ["ar", "en"] as const) {
			const text = composed("practice", lang);
			assert.ok(text.includes(MARK.practice), "practice appendix present");
			assert.ok(text.includes(MARK.shared), "shared doctrine present");
			assert.ok(text.includes(MARK.retention), "retention rule present");
			assert.ok(text.includes(MARK.anki), "Anki policy preserved");
		}
	});

	it("shared override reaches all three agents exactly once", () => {
		for (const kind of ["prober", "teacher", "practice"] as const) {
			const text = composed(kind);
			assert.equal(
				(text.match(new RegExp(MARK.shared, "g")) ?? []).length,
				1,
				`${kind}: shared appendix must appear once`,
			);
		}
	});

	it("every enabled segment uses its override text, not the source text", () => {
		for (const segment of manifest.segments) {
			const agent = segment.agents[0] as "prober" | "teacher" | "practice";
			const info = overrideOf(agent, segment.path);
			assert.equal(info.enabled, true, `${segment.path} must be enabled`);
			assert.ok(info.overrideText, `${segment.path} must have override text`);
			assert.notEqual(info.overrideText, info.sourceText, `${segment.path} must differ from source`);
			assert.ok(
				info.overrideText!.includes("learnharness-personal: generated file"),
				`${segment.path} override must carry the generated header`,
			);
		}
	});

	it("overrides apply regardless of app language (single override slot)", () => {
		const arTeacher = composed("teacher", "ar");
		const enTeacher = composed("teacher", "en");
		// One override slot serves every app language, so both compositions
		// carry the same installed-language appendix. This is documented.
		for (const marker of [MARK.teacher, MARK.nine, MARK.noStage]) {
			assert.ok(arTeacher.includes(marker), `ar teacher must include ${marker}`);
			assert.ok(enTeacher.includes(marker), `en teacher must include ${marker}`);
		}
	});
});
