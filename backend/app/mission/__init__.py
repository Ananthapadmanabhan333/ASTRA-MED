"""Phase 6: unified mission control.

* ``taxonomy``: sources, categories, data origins and the priority model shared by every module.
* ``events``: the mission event store (timestamp normalisation, prioritisation, de-duplication,
  persistence and live broadcast).
* ``alerts``: the unified alert centre (lifecycle, acknowledgement, resolution, audit trail). Rule
  alerts from the phase 2 monitor are mirrored; the monitor stays authoritative for them.
* ``orchestrator``: producers (monitor hooks, AI sweep, NASA space-weather scan, habitat
  environment, emergency runs, incident reports) feeding one queue, plus event correlation.
* ``sandbox``: the mission simulation sandbox (own engine, clock, speed, pause, reset, playback).
* ``analytics``, ``dashboard``, ``system``: read models for the command dashboard, analytics and
  reliability checks.
"""
