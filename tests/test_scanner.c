// Standalone behavioral checks: use the real pinned scanner without a parser runtime.
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

// ASCII fixtures suffice for these indentation and punctuation transitions.
// Column counts bytes, including tabs, just like Tree-sitter's get_column.
typedef struct {
  TSLexer lexer;
  const char *text;
  size_t position;
  size_t end;
  uint32_t column;
} TestLexer;

static void test_advance(TSLexer *lexer, bool skip) {
  (void)skip;
  TestLexer *test = (TestLexer *)lexer;
  if (!test->text[test->position]) return;
  test->column = test->text[test->position] == '\n' ? 0 : test->column + 1;
  test->position++;
  lexer->lookahead = (unsigned char)test->text[test->position];
}

static void test_mark_end(TSLexer *lexer) {
  TestLexer *test = (TestLexer *)lexer;
  test->end = test->position;
}

static uint32_t test_column(TSLexer *lexer) {
  return ((TestLexer *)lexer)->column;
}

static bool test_eof(const TSLexer *lexer) {
  const TestLexer *test = (const TestLexer *)lexer;
  return test->text[test->position] == '\0';
}

static bool scan(void *scanner, const char *text, uint32_t column,
                 const bool *valid, enum TokenType expected, bool succeeds) {
  TestLexer test = {
    .lexer = {
      .lookahead = (unsigned char)text[0],
      .advance = test_advance,
      .mark_end = test_mark_end,
      .get_column = test_column,
      .eof = test_eof,
    },
    .text = text,
    .column = column,
  };
  bool result = tree_sitter_bend_external_scanner_scan(scanner, &test.lexer, valid);
  CHECK(result == succeeds);
  if (result) {
    CHECK(test.lexer.result_symbol == expected);
    // All tested state transitions are zero-width tokens. Lookahead and skipped
    // indentation must not accidentally become part of the emitted token.
    CHECK(test.end == 0);
  }
  return result;
}

static const bool begin_body[ERROR_UNSAFE + 1] = {[BLOCK_BEGIN] = true};
static const bool begin_lambda[ERROR_UNSAFE + 1] = {[LAMBDA_BEGIN] = true};
static const bool end_body[ERROR_UNSAFE + 1] = {[BLOCK_END] = true};
static const bool lines[ERROR_UNSAFE + 1] = {[BLOCK_END] = true, [NEWLINE] = true};
static const bool tail[ERROR_UNSAFE + 1] = {[BLOCK_END] = true, [TAIL_BEGIN] = true};

static unsigned serialize(void *scanner, char *output) {
  unsigned char buffer[TREE_SITTER_SERIALIZATION_BUFFER_SIZE + 16];
  memset(buffer, 0xa5, sizeof(buffer));
  unsigned length = tree_sitter_bend_external_scanner_serialize(scanner, (char *)buffer);
  CHECK(length <= TREE_SITTER_SERIALIZATION_BUFFER_SIZE);
  for (unsigned i = length; i < sizeof(buffer); i++) CHECK(buffer[i] == 0xa5);
  memcpy(output, buffer, length);
  return length;
}

static void drain(void *scanner, unsigned depth) {
  for (unsigned i = 0; i < depth; i++) scan(scanner, "", 0, end_body, BLOCK_END, true);
  scan(scanner, "", 0, end_body, BLOCK_END, false);
}

static void check_nested_and_reset(void) {
  void *scanner = tree_sitter_bend_external_scanner_create();
  char buffer[TREE_SITTER_SERIALIZATION_BUFFER_SIZE];
  CHECK(serialize(scanner, buffer) == 0);
  scan(scanner, "x", 2, begin_body, BLOCK_BEGIN, true);
  scan(scanner, "x", 4, begin_body, BLOCK_BEGIN, true);
  scan(scanner, "x", 6, begin_lambda, LAMBDA_BEGIN, true);
  unsigned length = serialize(scanner, buffer);
  void *restored = tree_sitter_bend_external_scanner_create();
  tree_sitter_bend_external_scanner_deserialize(restored, buffer, length);
  for (unsigned i = 0; i < 2; i++) {
    void *current = i ? restored : scanner;
    scan(current, ":", 0, end_body, BLOCK_END, true); // lambda-only terminator
    scan(current, ":", 0, end_body, BLOCK_END, false); // ordinary body remains
    scan(current, "\n    # comment\n    x", 0, lines, NEWLINE, true);
    scan(current, "\n  x", 0, lines, BLOCK_END, true);
    scan(current, "\n  x", 0, lines, NEWLINE, true);
    scan(current, ")", 0, end_body, BLOCK_END, true);
    scan(current, ")", 0, end_body, BLOCK_END, false); // root cannot pop
  }
  scan(restored, "x", 3, begin_lambda, LAMBDA_BEGIN, true);
  tree_sitter_bend_external_scanner_deserialize(restored, NULL, 0);
  CHECK(serialize(restored, buffer) == 0);
  scan(restored, ":", 0, end_body, BLOCK_END, false);
  scan(restored, "\nx", 9, lines, NEWLINE, true);
  scan(restored, "x", 2, begin_body, BLOCK_BEGIN, true);
  drain(restored, 1);
  tree_sitter_bend_external_scanner_destroy(restored);
  tree_sitter_bend_external_scanner_destroy(scanner);
}

static void check_lambda_tail_and_indentation(void) {
  void *scanner = tree_sitter_bend_external_scanner_create();
  scan(scanner, "x", 2, begin_lambda, LAMBDA_BEGIN, true);
  scan(scanner, ";", 0, tail, BLOCK_END, false); // rewrite tail keeps lambda open
  scan(scanner, "\n    x", 0, tail, TAIL_BEGIN, true);
  scan(scanner, ";", 0, end_body, BLOCK_END, false); // tail is not a lambda
  scan(scanner, ")", 0, end_body, BLOCK_END, true);
  scan(scanner, ";", 0, end_body, BLOCK_END, true);
  scan(scanner, "x", 0, begin_body, BLOCK_BEGIN, false); // root column forbidden
  scan(scanner, "x", 2, begin_body, BLOCK_BEGIN, true);
  scan(scanner, "\n\t\tx", 0, lines, NEWLINE, true); // tab counts one column
  scan(scanner, "\n    case x", 0, lines, NEWLINE, true);
  scan(scanner, "\n    cases", 0, lines, NEWLINE, false); // keyword boundary
  scan(scanner, "\n    return.x", 0, lines, NEWLINE, false);
  scan(scanner, "\n    return x", 0, lines, NEWLINE, true);
  scan(scanner, "\nx", 0, lines, BLOCK_END, true);
  drain(scanner, 0);
  tree_sitter_bend_external_scanner_destroy(scanner);
}

static void check_serialization_boundaries(void) {
  void *scanner = tree_sitter_bend_external_scanner_create();
  void *restored = tree_sitter_bend_external_scanner_create();
  char buffer[TREE_SITTER_SERIALIZATION_BUFFER_SIZE];
  char again[TREE_SITTER_SERIALIZATION_BUFFER_SIZE];
  unsigned capacity = TREE_SITTER_SERIALIZATION_BUFFER_SIZE / 2;
  CHECK(TREE_SITTER_SERIALIZATION_BUFFER_SIZE % 2 == 0);
  char same_column[32770];
  same_column[0] = '\n';
  memset(same_column + 1, ' ', 32767);
  same_column[32768] = 'x';
  same_column[32769] = '\0';
  for (unsigned depth = 1; depth <= capacity; depth++) {
    // Both the lambda flag and the highest representable indentation survive.
    scan(scanner, "x", 32767, depth % 2 ? begin_lambda : begin_body,
         depth % 2 ? LAMBDA_BEGIN : BLOCK_BEGIN, true);
    unsigned length = serialize(scanner, buffer);
    CHECK(length == depth * 2);
    tree_sitter_bend_external_scanner_deserialize(restored, buffer, length);
    CHECK(serialize(restored, again) == length);
    CHECK(memcmp(buffer, again, length) == 0);
    scan(restored, same_column, 0, lines, NEWLINE, true);
    scan(restored, ":", 0, end_body, BLOCK_END, depth % 2 != 0);
    drain(restored, depth - (depth % 2));
  }
  unsigned length = serialize(scanner, buffer);
  // A truncated snapshot is a prefix of complete frames, not an all-or-nothing
  // format. An odd final byte must not be read or turned into a phantom frame.
  for (unsigned prefix = 0; prefix < length; prefix++) {
    char *exact = prefix ? malloc(prefix) : NULL;
    CHECK(prefix == 0 || exact != NULL);
    if (prefix) memcpy(exact, buffer, prefix);
    scan(restored, "x", 7, begin_lambda, LAMBDA_BEGIN, true);
    tree_sitter_bend_external_scanner_deserialize(restored, exact, prefix);
    unsigned frames = prefix / 2;
    CHECK(serialize(restored, again) == frames * 2);
    CHECK(memcmp(buffer, again, frames * 2) == 0);
    drain(restored, frames);
    free(exact);
  }
  drain(scanner, capacity);
  tree_sitter_bend_external_scanner_destroy(restored);
  tree_sitter_bend_external_scanner_destroy(scanner);
}

int main(void) {
  check_nested_and_reset();
  check_lambda_tail_and_indentation();
  check_serialization_boundaries();
  puts("Scanner: nested bodies/lambdas, tails, dedents, reset, truncation and serialization capacity passed.");
  puts("LIMIT: snapshots support at most 512 nested frames; deeper live stacks are silently truncated by the pinned scanner.");
  puts("LIMIT: indentation above 32767 is not representable without colliding with the lambda flag.");
  puts("LIMIT: this standalone ASCII lexer does not model parser recovery, Unicode or included ranges.");
  return 0;
}
