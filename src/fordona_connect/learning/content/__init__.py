"""Boost content, synced into the ``content_*`` tables.

``sync.ContentSyncService`` is the only writer. Answer keys
(``ContentQuestionRevision.correct_option_key`` and ``explanation``) live here and
must never be copied into a public schema.
"""
