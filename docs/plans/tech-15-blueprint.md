# TECH-15 Blueprint — Show Usernames on Reviews + Channel Names on Item Cards

## Files to Modify

1. `backend/schemas.py` — add `user_name` field to `ReviewResponse`
2. `backend/api/routes/reviews.py` — populate `user_name` from User relationship
3. `frontend/src/pages/ProductPage.jsx` — replace "Verified User" with `rev.user_name`
4. `frontend/src/components/ItemCard.jsx` — add channel username next to category chip

## Step 1 — Backend: Add user_name to ReviewResponse

In `schemas.py`, ReviewResponse (line 39), add after `user_photo_url`:
```python
user_name: Optional[str] = None
```

## Step 2 — Backend: Populate user_name in GET reviews

In `reviews.py`, the `get_reviews` endpoint (line 113). After fetching reviews, attach `user_name` to each review object:
```python
for r in reviews:
    r.user_name = r.user.first_name or r.user.username or "User"
```

## Step 3 — Frontend: Show username on review cards

In `ProductPage.jsx`, the review card section (~line 235), change:
```
<span className="text-xs font-bold text-gray-700">Verified User</span>
```
to:
```
<span className="text-xs font-bold text-gray-700">{rev.user_name || rev.user?.first_name || "User"}</span>
```

## Step 4 — Frontend: Add channel name to ItemCard

In `ItemCard.jsx`, line 103-105 area. Add channel username above or beside the category chip:
```jsx
{item.channel?.username && (
  <span className="text-[10px] text-gray-400 truncate">@{item.channel.username}</span>
)}
```
Place it above the category + location row, or replace the location placeholder with the channel name.

## Acceptance Criteria
- [ ] Reviews display actual user names instead of "Verified User"
- [ ] Item cards display the channel/group @username
- [ ] If user has no name, fallback to "User"
- [ ] If channel has no username, omit the label
