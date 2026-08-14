#!/usr/bin/env ruby

require "git/pr/release"

module GitPrReleaseQueryBatching
  # GitHub counts the URL-encoded search query toward its 256-character limit. The upstream
  # 256-character batch size therefore overflows once spaces and qualifiers are encoded.
  MAX_QUERY_LENGTH = 180
  QUALIFIER_COUNT = 3

  # OptionParser passes false for a --no-* option, while git-pr-release 2.5.0 assigns that value
  # directly to @no_fetch. Consume it here and apply the intended behavior after initialization.
  NO_FETCH = ARGV.delete("--no-fetch")

  def initialize
    super
    @no_fetch = true if NO_FETCH
  end

  def search_issue_numbers(query)
    tokens = query.split
    qualifiers = tokens.shift(QUALIFIER_COUNT)
    query_base = qualifiers.join(" ")
    batches = tokens.each_with_object([query_base]) do |sha, queries|
      candidate = "#{queries.last} #{sha}"
      if candidate.length >= MAX_QUERY_LENGTH
        queries << "#{query_base} #{sha}"
      else
        queries[-1] = candidate
      end
    end

    batches.flat_map { |batch| super(batch) }.uniq
  end
end

Git::Pr::Release::CLI.prepend(GitPrReleaseQueryBatching)
Git::Pr::Release::CLI.start
