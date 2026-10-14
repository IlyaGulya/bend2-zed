// Standalone behavioral checks against the real pinned external scanner.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "scanner.c"

#define CHECK(condition) do { \
  if (!(condition)) { \
    fprintf(stderr, "%s:%d: %s failed\n", __FILE__, __LINE__, #condition); \
    exit(1); \
  } \
} while (0)

// These fixtures model ASCII columns; the parser checks exercise real input.
typedef struct {
  TSLexer lexer;
  const char *text;
  size_t position, end;
  uint32_t column;
} TestLexer;

static void test_advance(TSLexer *lexer, bool skip) {
  (void)skip;
  TestLexer *test = (TestLexer *)lexer;
  if (!test->text[test->position]) return;
  test->column = test->text[test->position] == '\n' ? 0 : test->column + 1;
  lexer->lookahead = (unsigned char)test->text[++test->position];
}
static void test_mark_end(TSLexer *lexer) {
  TestLexer *test = (TestLexer *)lexer;
  test->end = test->position;
}
static uint32_t test_column(TSLexer *lexer) { return ((TestLexer *)lexer)->column; }
static bool test_eof(const TSLexer *lexer) {
  const TestLexer *test = (const TestLexer *)lexer;
  return test->text[test->position] == '\0';
}

static bool scan(void *scanner, const char *text, uint32_t column,
                 const bool *valid, enum Token expected, bool succeeds, size_t end) {
  TestLexer test = {
    .lexer = {.lookahead = (unsigned char)text[0], .advance = test_advance,
              .mark_end = test_mark_end, .get_column = test_column, .eof = test_eof},
    .text = text, .column = column,
  };
  bool result = tree_sitter_bend2_external_scanner_scan(scanner, &test.lexer, valid);
  if (result != succeeds || (result && (test.lexer.result_symbol != expected || test.end != end))) {
    fprintf(stderr, "scan(\"%s\", column=%u): result=%d token=%u end=%zu; expected result=%d token=%u end=%zu\n",
            text, column, result, (unsigned)test.lexer.result_symbol, test.end,
            succeeds, (unsigned)expected, end);
  }
  CHECK(result == succeeds);
  if (result) {
    CHECK(test.lexer.result_symbol == expected);
    CHECK(test.end == end);
  }
  return result;
}

#define TOKENS(...) ((const bool[ARRAY_LAYOUT + 1]){__VA_ARGS__})
#define STEP(s, text, column, token) \
  scan(s, text, column, TOKENS([token] = true), token, true, 0)

static unsigned serialize(void *scanner, char *output) {
  unsigned char buffer[TREE_SITTER_SERIALIZATION_BUFFER_SIZE + 16];
  memset(buffer, 0xa5, sizeof(buffer));
  unsigned length = tree_sitter_bend2_external_scanner_serialize(scanner, (char *)buffer);
  CHECK(length <= TREE_SITTER_SERIALIZATION_BUFFER_SIZE);
  for (unsigned i = length; i < sizeof(buffer); ++i) CHECK(buffer[i] == 0xa5);
  memcpy(output, buffer, length);
  return length;
}

static void enter_case(void *scanner, const char *text, uint32_t column) {
  scan(scanner, text, column, TOKENS([CASE] = true), CASE, true, 4);
  STEP(scanner, "x", column + 5, CASE_HEADER_START);
  STEP(scanner, "x", column + 7, CASE_BODY_START);
}

static void check_case_nesting_and_recovery(void) {
  void *scanner = tree_sitter_bend2_external_scanner_create();
  void *restored = tree_sitter_bend2_external_scanner_create();
  char buffer[TREE_SITTER_SERIALIZATION_BUFFER_SIZE];
  STEP(scanner, "x", 0, FUNCTION_START);
  STEP(scanner, "x", 2, MATCH_START);
  enter_case(scanner, "case x", 4);
  STEP(scanner, "x", 6, MATCH_START);
  enter_case(scanner, "case x", 8);
  unsigned length = serialize(scanner, buffer);
  tree_sitter_bend2_external_scanner_deserialize(restored, buffer, length);
  for (unsigned i = 0; i < 2; ++i) {
    void *current = i ? restored : scanner;
    STEP(current, ")", 0, ARM_END);
    STEP(current, "\n    case x", 0, MATCH_END); // outer arm, not inner sibling
    STEP(current, "\n    case x", 0, ARM_END);
    enter_case(current, "case x", 4);
    // Recovery closes the damaged arm before emitting its sibling's keyword.
    scan(current, "\n    case x", 0,
         TOKENS([ERROR_SENTINEL] = true, [DEF_KEYWORD] = true, [ARM_END] = true),
         ARM_END, true, 0);
    enter_case(current, "case x", 4);
    STEP(current, ")", 0, ARM_END);
    STEP(current, "\nx", 0, MATCH_END);
    STEP(current, ")", 0, BODY_END);
    scan(current, "", 0, TOKENS([BODY_END] = true), BODY_END, false, 0);
  }
  tree_sitter_bend2_external_scanner_destroy(restored);
  tree_sitter_bend2_external_scanner_destroy(scanner);
}

static void check_continuations_and_lexical_state(void) {
  void *scanner = tree_sitter_bend2_external_scanner_create();
  void *restored = tree_sitter_bend2_external_scanner_create();
  char buffer[TREE_SITTER_SERIALIZATION_BUFFER_SIZE];
  // Large columns and continuation ownership survive snapshots without packing.
  STEP(scanner, "x", 4000000000u, DO_START);
  STEP(scanner, "x", 3, LAMBDA_START);
  unsigned length = serialize(scanner, buffer);
  tree_sitter_bend2_external_scanner_deserialize(restored, buffer, length);
  for (unsigned i = 0; i < 2; ++i) {
    void *current = i ? restored : scanner;
    scan(current, ": U32 = x", 0, TOKENS([LAMBDA_END] = true), LAMBDA_END, false, 0);
    STEP(current, ": U32)", 0, LAMBDA_END); // enclosing annotation ends lambda
    STEP(current, "x", 4000000000u, DO_MORE);
    scan(current, "x", 3999999999u, TOKENS([DO_MORE] = true), DO_MORE, false, 0);
    STEP(current, ")", 0, DO_END);
  }
  scan(scanner, "def", 0, TOKENS([DEF_KEYWORD] = true), DEF_KEYWORD, true, 3);
  length = serialize(scanner, buffer);
  tree_sitter_bend2_external_scanner_deserialize(restored, buffer, length);
  for (unsigned i = 0; i < 2; ++i) {
    void *current = i ? restored : scanner;
    scan(current, "after", 4, TOKENS([ERROR_SENTINEL] = true, [DECLARATION_NAME] = true),
         DECLARATION_NAME, false, 0);
    STEP(current, "after", 4, HEADER_CHECKPOINT);
    scan(current, "after", 4, TOKENS([ERROR_SENTINEL] = true, [DECLARATION_NAME] = true),
         DECLARATION_NAME, true, 5);
    scan(current, "value", 4, TOKENS([ERROR_SENTINEL] = true, [DECLARATION_NAME] = true),
         DECLARATION_NAME, false, 0);
  }
  scan(scanner, "\"a\nb\"", 2, TOKENS([STRING_START] = true), STRING_START, true, 1);
  length = serialize(scanner, buffer);
  tree_sitter_bend2_external_scanner_deserialize(restored, buffer, length);
  scan(restored, "\n", 3, TOKENS([STRING_NEWLINE] = true), STRING_NEWLINE, true, 1);
  scan(restored, "\"unclosed\n", 2, TOKENS([STRING_START] = true), STRING_START, true, 1);
  length = serialize(restored, buffer);
  tree_sitter_bend2_external_scanner_deserialize(scanner, buffer, length);
  scan(scanner, "\n", 3, TOKENS([STRING_NEWLINE] = true), STRING_NEWLINE, false, 0);
  tree_sitter_bend2_external_scanner_destroy(restored);
  tree_sitter_bend2_external_scanner_destroy(scanner);
}

static void check_write_and_parallel_state(void) {
  void *scanner = tree_sitter_bend2_external_scanner_create();
  void *restored = tree_sitter_bend2_external_scanner_create();
  char buffer[TREE_SITTER_SERIALIZATION_BUFFER_SIZE];
  scan(scanner, "buf[0] <- 1", 4, TOKENS([WRITE_START] = true), WRITE_START, true, 3);
  STEP(scanner, "x", 6, PARALLEL_START);
  STEP(scanner, "y", 8, PARALLEL);
  unsigned length = serialize(scanner, buffer);
  tree_sitter_bend2_external_scanner_deserialize(restored, buffer, length);
  for (unsigned i = 0; i < 2; ++i) {
    void *current = i ? restored : scanner;
    for (unsigned value = 0; value < 3; ++value) STEP(current, "1", 10, PARALLEL_VALUE);
    STEP(current, ")", 0, PARALLEL_END);
    STEP(current, "x", 4, WRITE_MORE);
    scan(current, "x", 3, TOKENS([WRITE_MORE] = true), WRITE_MORE, false, 0);
    STEP(current, ")", 0, WRITE_END);
    scan(current, "", 0, TOKENS([ERROR_SENTINEL] = true), WRITE_END, false, 0);
  }
  tree_sitter_bend2_external_scanner_destroy(restored);
  tree_sitter_bend2_external_scanner_destroy(scanner);
}

static void check_snapshot_bounds_and_truncation(void) {
  void *scanner = tree_sitter_bend2_external_scanner_create();
  void *restored = tree_sitter_bend2_external_scanner_create();
  char buffer[TREE_SITTER_SERIALIZATION_BUFFER_SIZE];
  // Grow through public transitions until bounded state refuses another scope.
  // The refusal must preserve every already-open scope across serialization.
  unsigned depth = 0;
  while (depth < TREE_SITTER_SERIALIZATION_BUFFER_SIZE) {
    TestLexer lexer = {
      .lexer = {.lookahead = 'x', .advance = test_advance, .mark_end = test_mark_end,
                .get_column = test_column, .eof = test_eof}, .text = "x", .column = 2,
    };
    if (!tree_sitter_bend2_external_scanner_scan(scanner, &lexer.lexer,
        TOKENS([MATCH_START] = true))) break;
    CHECK(lexer.lexer.result_symbol == MATCH_START);
    ++depth;
    serialize(scanner, buffer);
  }
  CHECK(depth > 1 && depth < TREE_SITTER_SERIALIZATION_BUFFER_SIZE);
  unsigned length = serialize(scanner, buffer);
  tree_sitter_bend2_external_scanner_deserialize(restored, buffer, length);
  for (unsigned i = 0; i < depth; ++i) STEP(restored, "", 0, MATCH_END);
  scan(restored, "", 0, TOKENS([MATCH_END] = true), MATCH_END, false, 0);
  // Every incomplete snapshot is rejected in full, not restored as a prefix.
  for (unsigned prefix = 0; prefix < length; ++prefix) {
    char *exact = prefix ? malloc(prefix) : NULL;
    CHECK(!prefix || exact != NULL);
    if (prefix) memcpy(exact, buffer, prefix);
    STEP(restored, "x", 7, LAMBDA_START);
    tree_sitter_bend2_external_scanner_deserialize(restored, exact, prefix);
    scan(restored, "", 0, TOKENS([ERROR_SENTINEL] = true), BODY_END, false, 0);
    free(exact);
  }
  char oversized[TREE_SITTER_SERIALIZATION_BUFFER_SIZE + 1] = {0};
  STEP(restored, "x", 7, LAMBDA_START);
  tree_sitter_bend2_external_scanner_deserialize(restored, oversized, sizeof(oversized));
  scan(restored, "", 0, TOKENS([ERROR_SENTINEL] = true), BODY_END, false, 0);
  tree_sitter_bend2_external_scanner_deserialize(scanner, NULL, 0);
  scan(scanner, "", 0, TOKENS([ERROR_SENTINEL] = true), MATCH_END, false, 0);
  tree_sitter_bend2_external_scanner_destroy(restored);
  tree_sitter_bend2_external_scanner_destroy(scanner);
}

int main(void) {
  check_case_nesting_and_recovery();
  check_continuations_and_lexical_state();
  check_write_and_parallel_state();
  check_snapshot_bounds_and_truncation();
  puts("Scanner: case nesting/recovery, continuations, lambda boundaries, lexical state, snapshot roundtrips, bounds and truncation passed.");
  puts("LIMIT: this standalone ASCII lexer does not model parser recovery, Unicode or included ranges.");
  return 0;
}
