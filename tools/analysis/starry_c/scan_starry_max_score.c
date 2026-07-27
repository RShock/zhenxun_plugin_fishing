/*
 * High-efficiency starry fish full-space score scanner (000000-999999).
 *
 * Accelerations:
 *  1) Multi-thread partition (Win32 threads; OpenMP optional)
 *  2) No heap allocation on hot path
 *  3) Fixed 6-digit unrolled extract / window predicates
 *  4) Compact bitmask OK tables + maximal-window absorption
 *  5) Preloaded score constants
 *  6) Sequential ID scan (cache-friendly)
 *
 * Build (TinyCC):
 *   tcc -O2 -lkernel32 -o scan_starry_max_score.exe scan_starry_max_score.c
 * Build (GCC):
 *   gcc -O3 -march=native -fopenmp -DUSE_OPENMP -o scan_starry_max_score.exe scan_starry_max_score.c
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>
#include <time.h>

#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#endif

#define DIGITS 6
#define SPACE  1000000
#define MAX_BEST_IDS 64
#define MAX_TOP 32

/* Feature scores from starry_system.FEATURE_SCORE */
static const double S_SAME[7] = {0,0,0, 1.432856, 2.552842, 3.721246, 5.0};
static const double S_STEP[7] = {0,0,0, 1.227224, 2.402305, 3.638272, 5.0};
static const double S_SLIDE[7]= {0,0,0, 0.757901, 1.517984, 2.368759, 3.337242};
static const double S_PSNK[7] = {0,0,0, 1.180417, 1.874649, 2.698536, 3.653647};
static const double S_SNAK[7] = {0,0,0, 1.180417, 1.567993, 2.133004, 2.838033};
static const double S_PAL[7]  = {0,0,0, 0.505804, 1.570086, 1.705313, 3.004365};
static const double S_SMALL = 1.806180;
static const double S_BIG   = 1.806180;
static const double S_ODD   = 1.806180;
static const double S_EVEN  = 1.806180;
static const double S_ABAB  = 1.598599;
static const double S_ABABAB= 4.045757;
static const double S_ABCABC= 3.004365;
static const double S_AIR   = 1.899285;
static const double S_2PAIR = 1.595508;
static const double S_3PAIR = 3.091515;
static const double S_FH    = 2.454693;
static const double S_CHUNK = 2.658763;
static const double S_PIHU  = 0.802444;
static const double S_PERM[7] = {0,0,0,0, 1.444857, 1.947691, 2.443697}; /* 排列4/5/6 */

/* Window packing: index = length*8 + start  (length 3..6, start 0..3) */
static inline int wkey(int start, int length) { return (length << 3) | start; }

static inline int signi(int v) { return (v > 0) - (v < 0); }

static inline void extract_digits(int value, int d[DIGITS]) {
    d[0] = (value / 100000) % 10;
    d[1] = (value / 10000) % 10;
    d[2] = (value / 1000) % 10;
    d[3] = (value / 100) % 10;
    d[4] = (value / 10) % 10;
    d[5] = value % 10;
}

static int window_same(const int *d, int s, int len) {
    int v = d[s], i;
    for (i = 1; i < len; ++i) if (d[s + i] != v) return 0;
    return 1;
}

static int window_step(const int *d, int s, int len) {
    int diff = d[s + 1] - d[s], i;
    if (diff != 1 && diff != -1) return 0;
    for (i = 2; i < len; ++i)
        if (d[s + i] - d[s + i - 1] != diff) return 0;
    return 1;
}

static int window_slide(const int *d, int s, int len) {
    int all_up = 1, all_dn = 1, i, diff;
    for (i = 1; i < len; ++i) {
        diff = d[s + i] - d[s + i - 1];
        if (diff != 0 && diff != 1) all_up = 0;
        if (diff != 0 && diff != -1) all_dn = 0;
        if (!all_up && !all_dn) return 0;
    }
    return all_up || all_dn;
}

static int window_snake(const int *d, int s, int len, int pure) {
    int previous = 0, moved = 0, turned = 0, i, diff, dir;
    for (i = 1; i < len; ++i) {
        diff = d[s + i] - d[s + i - 1];
        if (pure) {
            if (diff != 1 && diff != -1) return 0;
        } else if (diff < -1 || diff > 1) {
            return 0;
        }
        dir = signi(diff);
        if (dir) {
            moved = 1;
            if (previous && dir != previous) turned = 1;
            previous = dir;
        }
    }
    return moved && turned;
}

static int window_pal(const int *d, int s, int len) {
    int i, half = len / 2;
    for (i = 0; i < half; ++i)
        if (d[s + i] != d[s + len - 1 - i]) return 0;
    return 1;
}

/* 排列x：窗口内所有数字互不相同，且排序后连续（max-min==len-1）。
 * 例如 4321 → {1,2,3,4} 连续 → 排列4；4231 → {1,2,3,4} 连续 → 排列4。
 * x 最低为 4。 */
static int window_perm(const int *d, int s, int len) {
    int i, j, mn, mx;
    for (i = 0; i < len; ++i)
        for (j = i + 1; j < len; ++j)
            if (d[s + i] == d[s + j]) return 0;
    mn = mx = d[s];
    for (i = 1; i < len; ++i) {
        if (d[s + i] < mn) mn = d[s + i];
        if (d[s + i] > mx) mx = d[s + i];
    }
    return mx - mn == len - 1;
}

/* bitset: bit = (length-3)*4 + start  covers all valid windows */
static inline int bit_of(int start, int length) {
    return (length - 3) * 4 + start;
}

static int contained_in_larger(unsigned ok, int start, int length) {
    int bigger, bs, end = start + length;
    for (bigger = length + 1; bigger <= DIGITS; ++bigger) {
        for (bs = 0; bs <= DIGITS - bigger; ++bs) {
            if (bs <= start && end <= bs + bigger) {
                if (ok & (1u << bit_of(bs, bigger))) return 1;
            }
        }
    }
    return 0;
}

static int motif_abab(const int *d, int s) {
    return d[s] == d[s + 2] && d[s + 1] == d[s + 3] && d[s] != d[s + 1];
}

static int motif_ababab(const int *d) {
    return d[0] != d[1] && d[0] == d[2] && d[0] == d[4]
        && d[1] == d[3] && d[1] == d[5];
}

static int motif_abcabc(const int *d) {
    int a = d[0], b = d[1], c = d[2];
    if (!(a == d[3] && b == d[4] && c == d[5])) return 0;
    if (a == b || a == c || b == c) return 0;
    return 1;
}

static int chunk_sequence(const int *d) {
    int t0 = d[0] * 10 + d[1];
    int t1 = d[2] * 10 + d[3];
    int t2 = d[4] * 10 + d[5];
    int d1 = t1 - t0, d2 = t2 - t1;
    if (d1 == d2 && (d1 == 1 || d1 == -1)) return 1;
    {
        int a = d[0] * 100 + d[1] * 10 + d[2];
        int b = d[3] * 100 + d[4] * 10 + d[5];
        int dd = b - a;
        if (dd == 1 || dd == -1) return 1;
    }
    return 0;
}

static int star_airplane(const int *d) {
    int i;
    for (i = 1; i <= 4; ++i)
        if (!(d[i] == d[i - 1] || d[i] == d[i + 1])) return 0;
    return 1;
}

/* New adjacency-based pair detection.
 * Returns 0 (none), 2 (two_pair), or 3 (three_pair).
 *
 * two_pair: two consecutive runs both with length >= 2 and different digits.
 * three_pair: exactly 3 runs of length 2 (covering all 6 digits),
 *   middle run's digit differs from both sides (sides may be same).
 * three_pair absorbs two_pair.
 */
static int detect_pairs(const int *d) {
    int run_digit[6], run_len[6], run_n = 0;
    int i = 0;
    while (i < DIGITS) {
        int end = i + 1;
        while (end < DIGITS && d[end] == d[i]) ++end;
        run_digit[run_n] = d[i];
        run_len[run_n] = end - i;
        run_n++;
        i = end;
    }

    /* three_pair: exactly 3 runs, each length 2, middle differs from both sides */
    if (run_n == 3 && run_len[0] == 2 && run_len[1] == 2 && run_len[2] == 2) {
        if (run_digit[1] != run_digit[0] && run_digit[1] != run_digit[2])
            return 3;
    }

    /* two_pair: consecutive runs both length >= 2 and different digits */
    for (i = 0; i < run_n - 1; ++i) {
        if (run_len[i] >= 2 && run_len[i+1] >= 2 && run_digit[i] != run_digit[i+1])
            return 2;
    }

    return 0;
}

static int full_house_any(const int *d) {
    int start;
    for (start = 0; start <= 1; ++start) {
        int run_n = 0, lens[5], idx = 0;
        while (idx < 5) {
            int end = idx + 1;
            while (end < 5 && d[start + end] == d[start + idx]) ++end;
            if (run_n < 5) lens[run_n++] = end - idx;
            idx = end;
        }
        if (run_n == 2 && ((lens[0] == 3 && lens[1] == 2) || (lens[0] == 2 && lens[1] == 3)))
            return 1;
    }
    return 0;
}

static double score_raw(int value) {
    int d[DIGITS];
    unsigned ok_same = 0, ok_step = 0, ok_slide = 0, ok_snake = 0, ok_pure = 0, ok_pal = 0, ok_perm = 0;
    int length, start;
    double total = 0.0;
    int hit = 0;
    int cnt[10];
    int i, maxc, pairs;

    extract_digits(value, d);

    for (length = 3; length <= DIGITS; ++length) {
        for (start = 0; start <= DIGITS - length; ++start) {
            unsigned bit = 1u << bit_of(start, length);
            if (window_same(d, start, length))  ok_same  |= bit;
            if (window_step(d, start, length))  ok_step  |= bit;
            if (window_slide(d, start, length)) ok_slide |= bit;
            if (window_snake(d, start, length, 1)) ok_pure |= bit;
            if (window_snake(d, start, length, 0)) ok_snake |= bit;
            if (window_pal(d, start, length))   ok_pal   |= bit;
            if (length >= 4 && window_perm(d, start, length)) ok_perm |= bit;
        }
    }

    if (d[0] <= 4 && d[1] <= 4 && d[2] <= 4 && d[3] <= 4 && d[4] <= 4 && d[5] <= 4) {
        total += S_SMALL; hit = 1;
    }
    if (d[0] >= 5 && d[1] >= 5 && d[2] >= 5 && d[3] >= 5 && d[4] >= 5 && d[5] >= 5) {
        total += S_BIG; hit = 1;
    }
    if ((d[0] & 1) && (d[1] & 1) && (d[2] & 1) && (d[3] & 1) && (d[4] & 1) && (d[5] & 1)) {
        total += S_ODD; hit = 1;
    }
    if (((d[0] | d[1] | d[2] | d[3] | d[4] | d[5]) & 1) == 0) {
        total += S_EVEN; hit = 1;
    }
    if (star_airplane(d)) { total += S_AIR; hit = 1; }

    for (length = 3; length <= DIGITS; ++length) {
        for (start = 0; start <= DIGITS - length; ++start) {
            unsigned bit = 1u << bit_of(start, length);
            if ((ok_same & bit) && !contained_in_larger(ok_same, start, length)) {
                total += S_SAME[length]; hit = 1;
            }
            if ((ok_slide & bit) && !contained_in_larger(ok_slide, start, length)) {
                if (ok_step & bit) total += S_STEP[length];
                else total += S_SLIDE[length];
                hit = 1;
            }
            if ((ok_snake & bit) && !contained_in_larger(ok_snake, start, length)) {
                if (ok_pure & bit) total += S_PSNK[length];
                else total += S_SNAK[length];
                hit = 1;
            }
            /* 同号吸收同号回文：被同号连段完全覆盖的回文不计分 */
            if ((ok_pal & bit) && !contained_in_larger(ok_pal, start, length)
                && !contained_in_larger(ok_same, start, length)) {
                total += S_PAL[length]; hit = 1;
            }
            /* 排列x：独立家族，大窗口吸收小窗口 */
            if (length >= 4 && (ok_perm & bit) && !contained_in_larger(ok_perm, start, length)) {
                total += S_PERM[length]; hit = 1;
            }
        }
    }

    if (motif_ababab(d)) {
        /* ABABAB 只吸收其内部三个 ABAB 窗口，其他家族照常累计。 */
        total += S_ABABAB; hit = 1;
    } else {
        for (start = 0; start <= 2; ++start) {
            if (motif_abab(d, start)) { total += S_ABAB; hit = 1; }
        }
    }
    if (motif_abcabc(d)) { total += S_ABCABC; hit = 1; }

    {
        /* 两对是葫芦的子牌型：命中葫芦时不单独计分，由葫芦吸收。 */
        int fh = full_house_any(d);
        pairs = detect_pairs(d);
        if (pairs >= 3) { total += S_3PAIR; hit = 1; }
        else if (pairs >= 2 && !fh) { total += S_2PAIR; hit = 1; }
        if (fh) { total += S_FH; hit = 1; }
    }
    if (chunk_sequence(d)) { total += S_CHUNK; hit = 1; }

    if (!hit) {
        memset(cnt, 0, sizeof(cnt));
        for (i = 0; i < DIGITS; ++i) cnt[d[i]]++;
        maxc = 0;
        for (i = 0; i < 10; ++i) if (cnt[i] > maxc) maxc = cnt[i];
        if (maxc >= 3) total += S_PIHU;
    }
    return total;
}

typedef struct {
    int start, end;
    double best_raw;
    int best_display;
    int best_ids[MAX_BEST_IDS];
    int best_count;
    double top_raw[MAX_TOP];
    int top_id[MAX_TOP];
    int top_n;
} WorkerResult;

static void top_consider(WorkerResult *w, double raw, int id) {
    int i, j;
    for (i = 0; i < w->top_n; ++i) {
        if (fabs(w->top_raw[i] - raw) < 1e-12) return; /* same raw already tracked */
        if (raw > w->top_raw[i]) break;
    }
    if (i >= MAX_TOP) return;
    if (w->top_n < MAX_TOP) w->top_n++;
    for (j = w->top_n - 1; j > i; --j) {
        w->top_raw[j] = w->top_raw[j - 1];
        w->top_id[j] = w->top_id[j - 1];
    }
    w->top_raw[i] = raw;
    w->top_id[i] = id;
}

static void worker_run(WorkerResult *w) {
    int v;
    w->best_raw = -1.0;
    w->best_display = -1;
    w->best_count = 0;
    w->top_n = 0;
    for (v = w->start; v < w->end; ++v) {
        double raw = score_raw(v);
        if (raw > w->best_raw + 1e-12) {
            w->best_raw = raw;
            w->best_display = (int)floor(raw + 0.5);
            w->best_count = 1;
            w->best_ids[0] = v;
        } else if (fabs(raw - w->best_raw) <= 1e-12) {
            if (w->best_count < MAX_BEST_IDS) w->best_ids[w->best_count++] = v;
            else w->best_count++; /* count beyond buffer */
        }
        top_consider(w, raw, v);
    }
}

#ifdef _WIN32
typedef struct { WorkerResult *w; } ThreadArg;
static DWORD WINAPI thread_entry(LPVOID p) {
    ThreadArg *a = (ThreadArg *)p;
    worker_run(a->w);
    return 0;
}
#else
static void *thread_entry(void *p) {
    WorkerResult *w = (WorkerResult *)p;
    worker_run(w);
    return NULL;
}
#endif

static void merge_results(WorkerResult *dst, const WorkerResult *src) {
    int i;
    if (src->best_raw > dst->best_raw + 1e-12) {
        *dst = *src; /* copy whole, then re-merge tops carefully */
        return;
    }
    if (fabs(src->best_raw - dst->best_raw) <= 1e-12) {
        for (i = 0; i < src->best_count && dst->best_count < MAX_BEST_IDS; ++i)
            dst->best_ids[dst->best_count++] = src->best_ids[i];
        if (src->best_count > i) {
            /* approximate full count */
            dst->best_count += (src->best_count - i);
        }
    }
    for (i = 0; i < src->top_n; ++i)
        top_consider(dst, src->top_raw[i], src->top_id[i]);
}

/* When first merge with empty dst */
static void merge_into(WorkerResult *acc, const WorkerResult *src, int *inited) {
    int i;
    if (!*inited) {
        *acc = *src;
        *inited = 1;
        return;
    }
    if (src->best_raw > acc->best_raw + 1e-12) {
        /* keep tops from both */
        WorkerResult keep = *acc;
        *acc = *src;
        for (i = 0; i < keep.top_n; ++i)
            top_consider(acc, keep.top_raw[i], keep.top_id[i]);
        return;
    }
    if (fabs(src->best_raw - acc->best_raw) <= 1e-12) {
        for (i = 0; i < src->best_count && acc->best_count < MAX_BEST_IDS; ++i)
            acc->best_ids[acc->best_count++] = src->best_ids[i];
    }
    for (i = 0; i < src->top_n; ++i)
        top_consider(acc, src->top_raw[i], src->top_id[i]);
}

static int parse_args(int argc, char **argv, int *threads, int *top, int *selftest, int *count, int *hist) {
    int i;
    *threads = 0;
    *top = 10;
    *selftest = 0;
    *count = 0;
    *hist = 0;
    for (i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--threads") && i + 1 < argc) {
            *threads = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--top") && i + 1 < argc) {
            *top = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--selftest")) {
            *selftest = 1;
        } else if (!strcmp(argv[i], "--count")) {
            *count = 1;
        } else if (!strcmp(argv[i], "--hist")) {
            *hist = 1;
        } else if (!strcmp(argv[i], "--help")) {
            printf("Usage: %s [--threads N] [--top K] [--selftest] [--count] [--hist]\n", argv[0]);
            return 1;
        }
    }
    return 0;
}

static int run_selftest(void) {
    /* Compare a few anchors against known Python results (current rules). */
    struct { int id; double raw; } cases[] = {
        {777777, 16.853252},
        {122221, 16.838223},
        {222422, 8.014234},
        {0, 0.0},
    };
    int i, fail = 0;
    for (i = 0; cases[i].id || i == 0; ++i) {
        double got = score_raw(cases[i].id);
        if (cases[i].id == 0 && i > 0) break;
        if (fabs(got - cases[i].raw) > 1e-5) {
            printf("SELFTEST FAIL id=%06d got=%.6f expect=%.6f\n",
                   cases[i].id, got, cases[i].raw);
            fail = 1;
        } else {
            printf("SELFTEST OK   id=%06d raw=%.6f\n", cases[i].id, got);
        }
        if (cases[i].id == 0) break;
    }
    /* also score 0 explicitly */
    {
        double got = score_raw(0);
        printf("SELFTEST id=000000 raw=%.6f display=%d\n", got, (int)floor(got + 0.5));
    }
    return fail;
}

int main(int argc, char **argv) {
    int threads = 0, top_n = 10, selftest = 0, count_mode = 0, hist_mode = 0;
    int i, chunk, rem, inited = 0;
    WorkerResult *workers;
    WorkerResult acc;
    double secs;
#ifdef _WIN32
    SYSTEM_INFO si;
    HANDLE *handles;
    ThreadArg *args;
    LARGE_INTEGER qpf, qpc0, qpc1;
#endif
#ifndef _WIN32
    clock_t t0, t1;
#endif

    if (parse_args(argc, argv, &threads, &top_n, &selftest, &count_mode, &hist_mode)) return 0;
    if (selftest) return run_selftest();

    if (hist_mode) {
        /* display_score 直方图：扫描全空间 000000..999999，
         * 统计每个展示分 floor(raw+0.5) 的计数与概率。
         * 同时输出奖池（reward_pool）汇总概率，与 starry_system.get_reward_pool 对齐：
         *   0 -> none / 1-2 low / 3-5 middle / 6-10 high / 11+ ultimate
         * 注意：C 版 display_score 上限约 32，数组开到 64 留余量。 */
        long long hist[64];
        long long pool_none = 0, pool_low = 0, pool_middle = 0, pool_high = 0, pool_ultimate = 0;
        long long total_raw_milli = 0; /* 千倍原始分累计，避免浮点漂移 */
        int max_disp = 0;
        double e_raw = 0.0, e_raw_sq = 0.0;
        memset(hist, 0, sizeof(hist));
        for (i = 0; i < SPACE; ++i) {
            double raw = score_raw(i);
            int disp = (int)floor(raw + 0.5);
            if (disp < 0) disp = 0;
            if (disp >= 64) disp = 63;
            hist[disp]++;
            e_raw += raw;
            e_raw_sq += raw * raw;
            if (disp > max_disp) max_disp = disp;
            if (disp <= 0) pool_none++;
            else if (disp <= 2) pool_low++;
            else if (disp <= 5) pool_middle++;
            else if (disp <= 10) pool_high++;
            else pool_ultimate++;
        }
        printf("=== DISPLAY_SCORE HISTOGRAM (space=000000..999999, n=%d) ===\n", SPACE);
        printf("E[raw_score]     = %.6f\n", e_raw / SPACE);
        printf("Std[raw_score]   = %.6f\n", sqrt(e_raw_sq / SPACE - (e_raw / SPACE) * (e_raw / SPACE)));
        {
            double e_disp = 0.0;
            for (i = 0; i <= max_disp; ++i) e_disp += (double)i * hist[i] / SPACE;
            printf("E[display_score] = %.6f\n", e_disp);
        }
        printf("display range    = 0 ~ %d\n", max_disp);
        printf("\n%-8s %-14s %-10s %s\n", "display", "count", "prob", "bar");
        for (i = 0; i <= max_disp; ++i) {
            double p = (double)hist[i] / SPACE;
            int barlen = (int)(p * 200.0 + 0.5);
            if (barlen > 60) barlen = 60;
            printf("%-8d %-14lld %.6f%%  %.*s\n", i, hist[i], p * 100.0, barlen,
                   "############################################################");
        }
        printf("\n=== REWARD POOL BREAKDOWN (get_reward_pool) ===\n");
        printf("%-12s %-14s %-10s\n", "pool", "count", "prob");
        printf("%-12s %-14lld %.6f%%\n", "none",     pool_none,     (double)pool_none / SPACE * 100.0);
        printf("%-12s %-14lld %.6f%%\n", "low",      pool_low,      (double)pool_low / SPACE * 100.0);
        printf("%-12s %-14lld %.6f%%\n", "middle",   pool_middle,   (double)pool_middle / SPACE * 100.0);
        printf("%-12s %-14lld %.6f%%\n", "high",     pool_high,     (double)pool_high / SPACE * 100.0);
        printf("%-12s %-14lld %.6f%%\n", "ultimate", pool_ultimate, (double)pool_ultimate / SPACE * 100.0);
        return 0;
    }

    if (count_mode) {
        long long two_pair_count = 0, three_pair_count = 0;
        long long perm4_count = 0, perm5_count = 0, perm6_count = 0;
        int d[DIGITS];
        for (i = 0; i < SPACE; ++i) {
            extract_digits(i, d);
            int p = detect_pairs(d);
            if (p >= 3) three_pair_count++;
            else if (p >= 2) two_pair_count++;

            /* 排列计数：同家族大窗口吸收小窗口 */
            {
                unsigned ok_perm = 0;
                int length, start;
                for (length = 4; length <= DIGITS; ++length) {
                    for (start = 0; start <= DIGITS - length; ++start) {
                        if (window_perm(d, start, length))
                            ok_perm |= 1u << bit_of(start, length);
                    }
                }
                int has4 = 0, has5 = 0, has6 = 0;
                for (length = 4; length <= DIGITS; ++length) {
                    for (start = 0; start <= DIGITS - length; ++start) {
                        unsigned bit = 1u << bit_of(start, length);
                        if ((ok_perm & bit) && !contained_in_larger(ok_perm, start, length)) {
                            if (length == 4) has4 = 1;
                            else if (length == 5) has5 = 1;
                            else if (length == 6) has6 = 1;
                        }
                    }
                }
                if (has4) perm4_count++;
                if (has5) perm5_count++;
                if (has6) perm6_count++;
            }
        }
        printf("=== PAIR COUNTS (new adjacency-based definition) ===\n");
        printf("two_pair_count: %lld\n", two_pair_count);
        printf("three_pair_count: %lld\n", three_pair_count);
        printf("two_pair_prob: %.12f\n", (double)two_pair_count / SPACE);
        printf("three_pair_prob: %.12f\n", (double)three_pair_count / SPACE);
        printf("two_pair_score: %.6f\n", -log10((double)two_pair_count / SPACE));
        printf("three_pair_score: %.6f\n", -log10((double)three_pair_count / SPACE));
        printf("\n=== PERM COUNTS (排列x: all distinct, sorted consecutive) ===\n");
        printf("perm4_count: %lld\n", perm4_count);
        printf("perm5_count: %lld\n", perm5_count);
        printf("perm6_count: %lld\n", perm6_count);
        printf("perm4_prob: %.12f\n", (double)perm4_count / SPACE);
        printf("perm5_prob: %.12f\n", (double)perm5_count / SPACE);
        printf("perm6_prob: %.12f\n", (double)perm6_count / SPACE);
        printf("perm4_score: %.6f\n", -log10((double)perm4_count / SPACE));
        printf("perm5_score: %.6f\n", -log10((double)perm5_count / SPACE));
        printf("perm6_score: %.6f\n", -log10((double)perm6_count / SPACE));
        return 0;
    }

#ifdef _WIN32
    GetSystemInfo(&si);
    if (threads <= 0) threads = (int)si.dwNumberOfProcessors;
#else
    if (threads <= 0) threads = 2;
#endif
    if (threads < 1) threads = 1;
    if (threads > 64) threads = 64;
    if (top_n < 1) top_n = 1;
    if (top_n > MAX_TOP) top_n = MAX_TOP;

    workers = (WorkerResult *)calloc((size_t)threads, sizeof(WorkerResult));
    if (!workers) { fprintf(stderr, "oom\n"); return 1; }

    chunk = SPACE / threads;
    rem = SPACE % threads;
    {
        int cursor = 0;
        for (i = 0; i < threads; ++i) {
            int n = chunk + (i < rem ? 1 : 0);
            workers[i].start = cursor;
            workers[i].end = cursor + n;
            cursor += n;
        }
    }

    printf("scan space=000000..999999 threads=%d\n", threads);
    fflush(stdout);
#ifdef _WIN32
    QueryPerformanceFrequency(&qpf);
    QueryPerformanceCounter(&qpc0);
#else
    t0 = clock();
#endif

#ifdef _WIN32
    handles = (HANDLE *)malloc(sizeof(HANDLE) * (size_t)threads);
    args = (ThreadArg *)malloc(sizeof(ThreadArg) * (size_t)threads);
    for (i = 0; i < threads; ++i) {
        args[i].w = &workers[i];
        handles[i] = CreateThread(NULL, 0, thread_entry, &args[i], 0, NULL);
        if (!handles[i]) {
            /* fallback sequential for this worker */
            worker_run(&workers[i]);
        }
    }
    for (i = 0; i < threads; ++i) {
        if (handles[i]) {
            WaitForSingleObject(handles[i], INFINITE);
            CloseHandle(handles[i]);
        }
    }
    free(handles);
    free(args);
#else
    {
        pthread_t *ths = (pthread_t *)malloc(sizeof(pthread_t) * (size_t)threads);
        for (i = 0; i < threads; ++i)
            pthread_create(&ths[i], NULL, thread_entry, &workers[i]);
        for (i = 0; i < threads; ++i)
            pthread_join(ths[i], NULL);
        free(ths);
    }
#endif

#ifdef _WIN32
    QueryPerformanceCounter(&qpc1);
    secs = (double)(qpc1.QuadPart - qpc0.QuadPart) / (double)qpf.QuadPart;
#else
    t1 = clock();
    secs = (double)(t1 - t0) / (double)CLOCKS_PER_SEC;
#endif

    memset(&acc, 0, sizeof(acc));
    acc.best_raw = -1.0;
    for (i = 0; i < threads; ++i)
        merge_into(&acc, &workers[i], &inited);

    printf("=== MAX ===\n");
    printf("max_raw: %.6f\n", acc.best_raw);
    printf("max_display: %d\n", acc.best_display);
    printf("count_at_max_buffered: %d\n", acc.best_count);
    printf("ids:");
    for (i = 0; i < acc.best_count && i < MAX_BEST_IDS; ++i)
        printf(" %06d", acc.best_ids[i]);
    printf("\n");
    printf("=== TOP %d distinct raw (sample id) ===\n", top_n);
    for (i = 0; i < acc.top_n && i < top_n; ++i) {
        printf("%06d raw=%.6f display=%d\n",
               acc.top_id[i], acc.top_raw[i], (int)floor(acc.top_raw[i] + 0.5));
    }
    printf("=== TIMING ===\n");
    printf("wall_clock_seconds: %.6f\n", secs);
    printf("ids_per_second: %.0f\n", SPACE / (secs > 1e-9 ? secs : 1e-9));
    printf("algorithms: multithread_partition, bitmask_windows, unrolled_digits, no_heap_hotpath, sequential_scan\n");

    free(workers);
    return 0;
}
