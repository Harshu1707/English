// Word Focus: a small, maintainable vocabulary list for the Practice page's
// "Word Focus" card, plus deterministic date-based selection so the word
// changes once per calendar day instead of on every page refresh.
//
// There was no existing word-list/API for this feature (it was a single
// hardcoded word in the page), so this adds the simplest thing that works:
// a plain array + a pure function of "today's date". No new backend
// endpoint or database table is needed — the Practice page already renders
// on the server per request, so recomputing this from today's date on each
// render is enough to keep it stable within a day and automatic the next.

export interface WordFocusItem {
  word: string;
  phonetic: string;
  meaning: string;
  example: string;
  cue: string; // short pronunciation tip, shown under "Helpful cue"
}

export const WORD_FOCUS_LIST: WordFocusItem[] = [
  {
    word: "communication",
    phonetic: "/kəˌmjuːnɪˈkeɪʃən/",
    meaning: "the sharing of information, ideas or feelings so others understand you",
    example: "Clear communication keeps a classroom calm and focused.",
    cue: "Let the stress settle on “-CA-”, without rushing the final syllables.",
  },
  {
    word: "articulate",
    phonetic: "/ɑːˈtɪkjʊleɪt/",
    meaning: "able to express thoughts clearly and effectively",
    example: "She gave an articulate explanation of the new grading policy.",
    cue: "Stress the second syllable, “-TIC-”, and keep each syllable distinct.",
  },
  {
    word: "eloquent",
    phonetic: "/ˈɛləkwənt/",
    meaning: "fluent and persuasive in speaking",
    example: "His eloquent introduction put the whole room at ease.",
    cue: "Stress falls on the first syllable; let the rest stay light and quick.",
  },
  {
    word: "confident",
    phonetic: "/ˈkɒnfɪdənt/",
    meaning: "sure of yourself and your abilities",
    example: "A confident tone helps students trust what you're teaching.",
    cue: "Stress the first syllable, “CON-”, and soften the final “-dent”.",
  },
  {
    word: "concise",
    phonetic: "/kənˈsaɪs/",
    meaning: "giving information clearly in a few words",
    example: "Keep your instructions concise so nothing gets lost.",
    cue: "The stress lands on “-CISE”; let the “s” sound crisp, not a “z”.",
  },
  {
    word: "empathetic",
    phonetic: "/ˌɛmpəˈθɛtɪk/",
    meaning: "able to understand and share another person's feelings",
    example: "An empathetic response can defuse a frustrated learner quickly.",
    cue: "Stress the third syllable, “-THET-”; the “th” is soft, as in “think”.",
  },
  {
    word: "engaging",
    phonetic: "/ɪnˈɡeɪdʒɪŋ/",
    meaning: "interesting and able to hold someone's attention",
    example: "An engaging opener makes the rest of the lesson easier.",
    cue: "Stress the middle syllable, “-GAG-”; the “g” is soft, as in “gentle”.",
  },
  {
    word: "assertive",
    phonetic: "/əˈsɜːtɪv/",
    meaning: "confident and direct without being aggressive",
    example: "Being assertive helps you set boundaries with kindness.",
    cue: "Stress the second syllable, “-SER-”; keep the final “-tive” short.",
  },
  {
    word: "fluent",
    phonetic: "/ˈfluːənt/",
    meaning: "able to speak smoothly and easily",
    example: "Daily practice is the fastest route to sounding fluent.",
    cue: "Two syllables only — let “flu-” glide straight into “-ent”.",
  },
  {
    word: "persuasive",
    phonetic: "/pəˈsweɪsɪv/",
    meaning: "good at convincing people to agree or act",
    example: "A persuasive argument relies on tone as much as words.",
    cue: "Stress the second syllable, “-SUA-”; the “s” here sounds like “z”.",
  },
];

/** Days since a fixed reference date (2024-01-01 UTC), used as a stable index. */
function dayIndex(date: Date): number {
  const REFERENCE = Date.UTC(2024, 0, 1);
  const startOfDay = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
  return Math.floor((startOfDay - REFERENCE) / 86_400_000);
}

/**
 * Deterministically picks today's Word Focus item. Same calendar day always
 * returns the same word; consecutive days step to a different list index
 * (so there's no back-to-back repeat as long as the list has more than one
 * word), and every day the whole list has been used once before any word
 * repeats.
 */
export function getDailyWordFocus(date: Date = new Date()): WordFocusItem {
  const list = WORD_FOCUS_LIST;
  const index = ((dayIndex(date) % list.length) + list.length) % list.length;
  return list[index];
}
