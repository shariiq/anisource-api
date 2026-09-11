#define PY_SSIZE_T_CLEAN
#include <stdint.h>
#include <string.h>
#include <stdio.h>

#define BUFFER_SIZE 512
#define BUFFER_MASK 511
#define INIT_CONST 2654435761U
#define FINAL_CONST 2246822519U

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

static inline uint32_t rotl32(uint32_t value, int shift) {
    return (value << shift) | (value >> (32 - shift));
}

static inline int count_leading_zeros32(uint32_t value) {
    if (value == 0) return 32;
    int lz = 0;
    if ((value & 0xFFFF0000) == 0) { lz += 16; value <<= 16; }
    if ((value & 0xFF000000) == 0) { lz += 8; value <<= 8; }
    if ((value & 0xF0000000) == 0) { lz += 4; value <<= 4; }
    if ((value & 0xC0000000) == 0) { lz += 2; value <<= 2; }
    if ((value & 0x80000000) == 0) { lz += 1; }
    return lz;
}

static inline void mix(uint32_t *s0, uint32_t *s1, uint32_t *s2, uint32_t *s3) {
    *s0 = (*s0 + *s1);
    *s3 = rotl32(*s3 ^ *s0, 16);
    *s2 = (*s2 + *s3);
    *s1 = rotl32(*s1 ^ *s2, 12);
    *s0 = (*s0 + *s1);
    *s3 = rotl32(*s3 ^ *s0, 8);
    *s2 = (*s2 + *s3);
    *s1 = rotl32(*s1 ^ *s2, 7);
}

EXPORT int solve_byse_pow_c(const char *nonce, int difficulty, int max_iterations) {
    size_t nonce_len = strlen(nonce);
    char prefix[256];
    if (nonce_len > 253) {
        return -1;
    }
    snprintf(prefix, sizeof(prefix), "%s:", nonce);

    uint32_t buf[BUFFER_SIZE];

    for (int counter = 0; counter <= max_iterations; counter++) {
        char input[280];
        snprintf(input, sizeof(input), "%s%d", prefix, counter);
        size_t input_len = strlen(input);

        uint32_t s0 = 1779033703;
        uint32_t s1 = 3144134277;
        uint32_t s2 = 1013904242;
        uint32_t s3 = 2773480762;

        for (size_t i = 0; i < input_len; i++) {
            s0 = (s0 + (uint8_t)input[i]);
            s0 = rotl32(s0, 7);
            mix(&s0, &s1, &s2, &s3);
        }

        for (int i = 0; i < 8; i++) {
            mix(&s0, &s1, &s2, &s3);
        }

        for (int i = 0; i < BUFFER_SIZE; i++) {
            mix(&s0, &s1, &s2, &s3);
            buf[i] = s0 ^ s2;
        }

        for (int pass = 0; pass < 2; pass++) {
            for (int si = 0; si < BUFFER_SIZE; si++) {
                uint32_t a = buf[si] & BUFFER_MASK;
                uint32_t c = buf[si] + buf[a];
                c = rotl32(c, 13);
                c = c ^ (buf[(si + 1) & BUFFER_MASK] * INIT_CONST);
                buf[si] = c;
                s0 = s0 ^ c;
                mix(&s0, &s1, &s2, &s3);
            }
        }

        mix(&s0, &s1, &s2, &s3);

        uint32_t out_val = s0;
        for (int ci = 0; ci < 64; ci++) {
            uint32_t d = buf[ci];
            out_val = out_val + d;
            out_val = rotl32(out_val, 5);
            out_val = out_val ^ (d * FINAL_CONST);
        }
        out_val = out_val ^ s2;

        if (count_leading_zeros32(out_val) >= difficulty) {
            return counter;
        }
    }

    return -1;
}
