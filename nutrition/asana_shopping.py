"""Asana shopping list integration for the AI Nutritionist.

Auto-adds ingredients to a designated Asana project as tasks,
so they appear on your phone as a shopping list.
"""

from __future__ import annotations

import os
from typing import Any

import asana
from asana.rest import ApiException
from hevy.env import load_dotenv

load_dotenv()  # ensure .env vars are loaded


class AsanaShoppingList:
    """Sync ingredients to an Asana project as tasks.

    Requires:
      - ASANA_ACCESS_TOKEN env var (Personal Access Token)
      - ASANA_SHOPPING_PROJECT_GID env var (the project/task list to add to)

    Get a PAT at: https://app.asana.com/0/developer-console
    """

    def __init__(
        self,
        access_token: str | None = None,
        project_gid: str | None = None,
    ) -> None:
        self._token = access_token or os.environ.get("ASANA_ACCESS_TOKEN", "")
        self._project = project_gid or os.environ.get("ASANA_SHOPPING_PROJECT_GID", "")

        if not self._token:
            raise ValueError(
                "Asana access token required. Set ASANA_ACCESS_TOKEN env var "
                "or pass access_token=."
            )
        if not self._project:
            raise ValueError(
                "Asana project GID required. Set ASANA_SHOPPING_PROJECT_GID env var "
                "or pass project_gid=."
            )

        config = asana.Configuration()
        config.access_token = self._token
        self._client = asana.ApiClient(config)
        self._tasks = asana.TasksApi(self._client)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_ingredient(
        self,
        name: str,
        notes: str = "",
        due_on: str | None = None,
    ) -> dict[str, Any] | None:
        """Add a single ingredient to the shopping list.

        Args:
            name: The ingredient name (e.g. "Kipfilet 500g", "Volle melk").
            notes: Optional details (brand, quantity, store).
            due_on: Optional ISO date for when it's needed (e.g. "2026-05-10").

        Returns:
            The created task object, or None on failure.
        """
        return self._create_task(name, notes=notes, due_on=due_on)

    def add_ingredients(
        self,
        ingredients: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Add multiple ingredients at once.

        Args:
            ingredients: List of dicts with keys: name, notes (optional), due_on (optional).

        Returns:
            List of created task objects.
        """
        results: list[dict[str, Any]] = []
        for item in ingredients:
            task = self._create_task(
                item["name"],
                notes=item.get("notes", ""),
                due_on=item.get("due_on"),
            )
            if task:
                results.append(task)
        return results

    def list_shopping_tasks(self) -> list[dict[str, Any]]:
        """Fetch all incomplete tasks from the shopping project.

        Useful to check what's already on the list before adding duplicates.
        """
        try:
            tasks = self._tasks.get_tasks_for_project(
                self._project,
                {"completed_since": "now", "opt_fields": "gid,name,notes,due_on"},
            )
            return list(tasks)
        except ApiException as e:
            print(f"Asana API error: {e}")
            return []

    def complete_task(self, task_gid: str) -> bool:
        """Mark a shopping task as complete."""
        try:
            self._tasks.update_task(task_gid, {"data": {"completed": True}})
            return True
        except ApiException as e:
            print(f"Failed to complete task: {e}")
            return False

    def is_already_on_list(self, name: str) -> bool:
        """Check if an ingredient is already on the shopping list (by name)."""
        tasks = self.list_shopping_tasks()
        return any(t["name"].lower() == name.lower() for t in tasks)

    def clear_completed(self) -> int:
        """Remove all completed tasks from the shopping list."""
        try:
            tasks = self._tasks.get_tasks_for_project(
                self._project,
                {"completed": True, "opt_fields": "gid"},
            )
            count = 0
            for t in tasks:
                self._tasks.delete_task(t["gid"])
                count += 1
            return count
        except ApiException as e:
            print(f"Failed to clear completed tasks: {e}")
            return 0

    def close(self) -> None:
        try:
            self._client.close()
        except AttributeError:
            pass  # older asana clients don't expose close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _create_task(
        self,
        name: str,
        notes: str = "",
        due_on: str | None = None,
    ) -> dict[str, Any] | None:
        """Create a task in the shopping project."""
        body: dict[str, Any] = {
            "data": {
                "name": name,
                "projects": [self._project],
                "notes": notes,
            }
        }
        if due_on:
            body["data"]["due_on"] = due_on

        try:
            task = self._tasks.create_task(body, {"opt_fields": "gid,name,due_on,projects.name"})
            return task
        except ApiException as e:
            print(f"Asana API error creating task '{name}': {e}")
            return None

    def __enter__(self) -> AsanaShoppingList:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
