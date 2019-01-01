#!/bin/bash
for i in {1..30}
do
   date="2025-0$(($i%9+1))-$((($i%28+1))) 12:00:00"
   echo "Contribution $i" >> activity.txt
   git add activity.txt
   GIT_AUTHOR_DATE="$date" GIT_COMMITTER_DATE="$date" git commit -m "Commit $i"
done