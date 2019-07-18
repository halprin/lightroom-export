# https://github.com/philroche/py-lightroom-export
# https://github.com/patrikhson/photo-export
# https://photo.stackexchange.com/questions/93172/where-can-i-find-lightroom-database-documentation
# https://macosxautomation.com/applescript/imageevents/index.html
# https://discussions.apple.com/thread/6874314

# com.adobe.ag.library.group = folder
# com.adobe.ag.library.collection = album


import sqlite3
from typing import Optional, List, Tuple
import applescript
from xml.etree import ElementTree
import datetime
import exifread
from os import path
import os
import sys
from timezonefinder import TimezoneFinder
import time
import subprocess
import shutil


tf = TimezoneFinder()


create_album_apple_script_root = applescript.AppleScript("""on run album_name
                                                tell application "Photos"
                                                    make new album named album_name
                                                end tell
                                            end run""")

create_album_apple_script = applescript.AppleScript("""on run {album_name, parent_name}
                                                tell application "Photos"
                                                    set parent_folder to folder named parent_name
                                                    make new album named album_name at parent_folder
                                                end tell
                                            end run""")

create_folder_apple_script_root = applescript.AppleScript("""on run folder_name
                                                tell application "Photos"
                                                    make new folder named folder_name
                                                end tell
                                            end run""")

create_folder_apple_script = applescript.AppleScript("""on run {folder_name, parent_name}
                                                tell application "Photos"
                                                    set parent_folder to folder named parent_name
                                                    make new folder named folder_name at parent_folder
                                                end tell
                                            end run""")

import_photo_apple_script = applescript.AppleScript("""on run photo_path
                                              tell application "Photos"
                                                  import photo_path skip check duplicates true
                                              end tell
                                          end run""")

set_metadata_apple_script = applescript.AppleScript("""on run {photo_id, photo_name, date_time, rating, latitude, longitude, photo_keywords}
                                                       tell application "Photos"
                                                           if photo_name is not current application then
                                                               set name of media item id photo_id to photo_name
                                                           end if
                                                           if date_time is not current application then
                                                               set date of media item id photo_id to date date_time
                                                           end if
                                                           if rating is equal to 4 or rating is equal to 5 then
                                                               set favorite of media item id photo_id to true
                                                           end if
                                                           if latitude is not current application and longitude is not current application then
                                                               set location of media item id photo_id to {latitude, longitude}
                                                           end if
                                                           set keywords of media item id photo_id to photo_keywords
                                                       end tell
                                                   end run""")

assign_album_apple_script = applescript.AppleScript("""on run {photo_id, album_id}
                                                           tell application "Photos"
                                                               add {media item id photo_id} to album id album_id
                                                           end tell
                                                       end run""")


quit_photos_apple_script = applescript.AppleScript("""tell application "Photos"
                                                           quit
                                                       end tell""")


start_photos_apple_script = applescript.AppleScript("""tell application "Photos"
                                                           activate
                                                       end tell""")

get_photos_selection_apple_script = applescript.AppleScript("""tell application "Photos"
    get selection
end tell""")

get_photos_date_for_id_apple_script = applescript.AppleScript("""on run {photo_id}
tell application "Photos"
    date of media item id photo_id
end tell
end run""")

go_down_selection_photos_apple_script = applescript.AppleScript("""tell application "Photos"
    activate
end tell

tell application "System Events"
    tell process "Photos"
        key code 125
    end tell
end tell
""")

change_timezone_photos_apple_script = applescript.AppleScript("""on chooseMenuItem(theAppName, theMenuName, theMenuItemName)
    try
        tell application theAppName
            activate
        end tell
        
        tell application "System Events"
            tell process theAppName
                tell menu bar 1
                    tell menu bar item theMenuName
                        tell menu theMenuName
                            click menu item theMenuItemName
                        end tell
                    end tell
                end tell
            end tell
        end tell
        
        delay 1.0
        
        return true
    on error
        return false
    end try
end chooseMenuItem

on setClosestCity(theAppName, theTimeZone)
    try
        tell application "Finder"
            activate
        end tell
        
        tell application "System Events"
            tell process theAppName
                tell combo box 1 of first sheet of window 1
                    set focused to true
                    set value to theTimeZone
                end tell
                
                delay 0.5
                
                set focused of UI element 6 of sheet 1 of window 1 to true
                delay 0.5
            end tell
        end tell
        return true
    on error
        return false
    end try
end setClosestCity

on setDateTime(theAppName, theMonth, theDay, theYear, theHour, theMinute, theSecond, theMeridian)
    try
        tell application "Photos"
            activate
        end tell
        
        tell application "System Events"
            tell process theAppName
                tell UI element 6 of sheet of window 1
                    set focused to true
                end tell
                keystroke theMonth
                keystroke "	"
                keystroke theDay
                keystroke "	"
                keystroke theYear
                keystroke "	"
                keystroke theHour
                keystroke "	"
                keystroke theMinute
                keystroke "	"
                keystroke theSecond
                keystroke "	"
                keystroke theMeridian
            end tell
        end tell
        
        delay 0.5
        
        return true
    on error
        return false
    end try
end setDateTime

on clickButton(theAppName, theButtonName)
    try
        tell application "Finder"
            activate
        end tell
        
        tell application "System Events"
            tell process theAppName
                click button theButtonName of sheet of window 1
            end tell
        end tell
        return true
    on error
        return false
    end try
end clickButton

on run {closestCity, theMonth, theDay, theYear, theHour, theMinute, theSecond, theMeridian}
    chooseMenuItem("Photos", "Image", "Adjust Date and Time...")
    setClosestCity("Photos", closestCity)
    setDateTime("Photos", theMonth, theDay, theYear, theHour, theMinute, theSecond, theMeridian)
    clickButton("Photos", "Adjust")
end run
""")


lighroom_edits_folder = '/Users/someone/Pictures/Lightroom/Edits/Real Edits/'


timezone_to_apple_closest_city = {
    'Africa/Cairo': 'Cairo - Egypt',
    'Africa/Freetown': 'Freetown - Sierra Leone',
    'America/Chicago': 'Chicago, IL - United States',
    'America/Denver': 'Denver, CO - United States',
    'America/La_Paz': 'La Paz - Bolivia',
    'America/Los_Angeles': 'Los Angeles, CA - United States',
    'America/Mexico_City': 'Mexico City - Mexico',
    'America/New_York': 'New York, NY - United States',
    'Asia/Bangkok': 'Bangkok - Thailand',
    'Europe/Amsterdam': 'Amsterdam - Netherlands',
    'Europe/Berlin': 'Berlin - Germany',
    'Europe/London': 'London - United Kingdom',
    'Europe/Paris': 'Paris - France',
    'Europe/Rome': 'Rome - Italy',
    'Europe/Zurich': 'Zürich - Switzerland',
    'America/Phoenix': 'Phoenix, AZ - United States',
    'America/Detroit': 'Detroit, MI - United States',
    'America/Ojinaga': 'Ciudad Juárez - Mexico',
    'America/Boise': 'Boise, ID - United States',
    'America/Nassau': 'Nassau - Bahamas'
}

apple_closest_city_to_timezone = {
    'Cairo - Egypt': 'Africa/Cairo',
    'Freetown - Sierra Leone': 'Africa/Freetown',
    'Chicago, IL - United States': 'America/Chicago',
    'Denver, CO - United States': 'America/Denver',
    'La Paz - Bolivia': 'America/La_Paz',
    'Los Angeles, CA - United States': 'America/Los_Angeles',
    'Mexico City - Mexico': 'America/Mexico_City',
    'New York, NY - United States': 'America/New_York',
    'Bangkok - Thailand': 'Asia/Bangkok',
    'Amsterdam - Netherlands': 'Europe/Amsterdam',
    'Berlin - Germany': 'Europe/Berlin',
    'London - United Kingdom': 'Europe/London',
    'Paris - France': 'Europe/Paris',
    'Rome - Italy': 'Europe/Rome',
    'Zürich - Switzerland': 'Europe/Zurich',
    'Phoenix, AZ - United States': 'America/Phoenix',
    'Detroit, MI - United States': 'America/Detroit',
    'Ciudad Juárez - Mexico': 'America/Ojinaga',
    'Boise, ID - United States': 'America/Boise',
    'Nassau - Bahamas': 'America/Nassau'
}

try_again_timezone = {'Y7nEt4KiSvuTdGl%YLNdsA': 'New York, NY - United States', '4g5kjFC+QneKs45XsLjVbA': 'New York, NY - United States', 'udSditqNRIuU6KWTKR3tUA': 'New York, NY - United States', 'hpKf5wfeQXOJgzjOBU5WeA': 'New York, NY - United States', 'h1PceF4yRzC+FUW+rVrjjQ': 'New York, NY - United States', 'Qe3pIZ92QryY%maWlzrBpA': 'New York, NY - United States', 'tguCfF+XRP+v4ftVxa3ouQ': 'New York, NY - United States', 'OCsyi9oRR%SLV9leF1RG%Q': 'Los Angeles, CA - United States', 'K5nuUa1rQGKzHBbBF0eCtA': 'New York, NY - United States', 'FoDlxVrCSB6waz+4HIAQBg': 'New York, NY - United States', 't7zk87fvQ92FYAyMmgxaRA': 'New York, NY - United States', 'MTGN3cuISe6AbqfUKg%ArA': 'New York, NY - United States', 'UVRQh0cgQiWWkNIqe2e1Qg': 'New York, NY - United States', 'r4i9X7AFSbauxCh3jP9yXg': 'New York, NY - United States', 'gX+Ig1NbTAqbAcOVqEbXDQ': 'New York, NY - United States', 'sWcR%TsEQQ6ihQy1lBAmGg': 'New York, NY - United States', 'i6FPoNzJR8SXgg5FmK5fOg': 'New York, NY - United States', 'fDMwBxkQRDqAcTYmPY8PmQ': 'New York, NY - United States', 'hBkTBBbJShm8RvScqTHrmQ': 'New York, NY - United States', 'MmJXdLFiTeyhelu2+Ep05g': 'New York, NY - United States', 'A4beH8KOSpCkapYAXQlVwQ': 'New York, NY - United States', 'vyQSsaXGSAy7FdAOXLQewA': 'New York, NY - United States', 'D3bg3mk6SGa1m2jJ1E26yg': 'New York, NY - United States', 'q5+a%s0RQjauB2xHaqZU4w': 'New York, NY - United States', 'AxqILHYJSbSfu19DNCILfA': 'Los Angeles, CA - United States', 'icCz06WWTrqnDYn94k1QbQ': 'New York, NY - United States', 'RIeBnFTdT%iIFmNSOqs3gg': 'New York, NY - United States', 'fqjcJIe7T6WkMB90WHXXPw': 'New York, NY - United States', 'D%eVoqx9Ro+VaYXvrhYtvw': 'Los Angeles, CA - United States', '1ESLoCKdR12eklcWeEGDrw': 'New York, NY - United States', 'TChj02VWRa6A0rt+jPAjWA': 'New York, NY - United States', 'nCgLVcXtRfW%lDnCqaglZQ': 'New York, NY - United States', 'wQfSFwU0SlKNhbyjwgZDfQ': 'New York, NY - United States', 'K4dR97OiRraAxW62NzUCXw': 'New York, NY - United States', 'gpfP5m%vQ8OLqMnPOStXBQ': 'New York, NY - United States', '++hjNHTVS4qID3hUjsSttw': 'Los Angeles, CA - United States', 'L92hZsakSCyCB1gD6qyunw': 'Los Angeles, CA - United States', 'uvFYodwaQme45AbRgAULpg': 'New York, NY - United States', 'qwXpFathTx+bJNQumZ3xVg': 'New York, NY - United States', 'nRUd9DRaR96c66Nak2hRsQ': 'New York, NY - United States', 'HIpmHaJBQGSiqV3kJahBww': 'New York, NY - United States', '2YyTahpBQViC8vHd15WcBQ': 'New York, NY - United States', 'zxQu86uRSAOJR6H2S04kNQ': 'New York, NY - United States', '5fPjbV7CSFGkGa+xQ0v9%Q': 'New York, NY - United States', 'Kza2SAqSSq6%C00sP4Zt3w': 'New York, NY - United States', 'lnTj5KuYTvmy4GFIjPFczA': 'New York, NY - United States', '8e%Bik98S8WLUuU7AZxkJg': 'New York, NY - United States', '0Od2f5StSDimPoapRhWUZw': 'Los Angeles, CA - United States', 'K5C1GMi+SFq2mji40QePjg': 'New York, NY - United States', '35NjiCPdS7mnDrZi0w27ag': 'New York, NY - United States', 'FhJWotPtSbeVxg7Z4GEwlw': 'New York, NY - United States', 'XdLB+DcUS1mvSDu9bLhlKg': 'New York, NY - United States', 'UTGDkqCsSlu6aF+Fj4ng8g': 'New York, NY - United States', 'HU3qcGQ7Rly9CA%U%Af8Rg': 'New York, NY - United States', 'ol8zkbXuRZauSM2iZIEt9g': 'New York, NY - United States', 'gd+t8dkgTQSLGkg+G%bCMw': 'New York, NY - United States', 'MQBo1KQjR3+fVboTDo0hEg': 'New York, NY - United States', '7MEVkq3FTSGiW9Jh+mopVw': 'New York, NY - United States', '%wwOZrErTnykByuTfUYKOw': 'New York, NY - United States', 'UtfPwzQeTAKT2AlJemk9uQ': 'New York, NY - United States', '725VY3mbSqaIh8AB0JknFQ': 'New York, NY - United States', 'xpGPQwkmQDi+ObJgh5A7Ow': 'New York, NY - United States', 'GxPjXcCMSlSRB6ufToWIZg': 'New York, NY - United States', '2TZyXSd6TAenP0k%2hwZeA': 'New York, NY - United States', '99rooSZvQGmuQFXoNNE3BQ': 'New York, NY - United States', 'ntxBegrdSBOv0949U9r+Xw': 'New York, NY - United States', 'kwE2gz2ET7mgjditvBDNWw': 'New York, NY - United States', 'fUOi6qRbTZGD+ynYRAd0bw': 'New York, NY - United States', 'xNrxvdbdT8iVAL4T2mKRNg': 'New York, NY - United States', 'YN5JFhPnRT2P70NLu40sCw': 'New York, NY - United States', 'XvVJyagWTIuEk981HViXrg': 'New York, NY - United States', 'wj6oeWKRQ8G3OzW0oTrUDQ': 'Los Angeles, CA - United States', 'CG4fXCJySqOl%O6MLMVM6g': 'New York, NY - United States', 'iORj%AlMQnGEIunBkilgOg': 'Los Angeles, CA - United States', 'qoKy1bcNRF+GA0mOHePPzg': 'Los Angeles, CA - United States', 'gCC9IDkJTgGx3PomndBAqg': 'Los Angeles, CA - United States', 'IrQXqOygQP+e%BEbwX95uQ': 'New York, NY - United States', '3RJ3sOJ7SPOUzb8YrbwPIQ': 'New York, NY - United States', 'it4caC53T8qrylx6n04r5Q': 'New York, NY - United States', 'YqurQ9kxSPS49Kd1fuXqFg': 'New York, NY - United States', '75WNVWk7TsiSYG3jwmhhQA': 'New York, NY - United States', 'lNAACZ7fSvCaB8ht2gcTqw': 'New York, NY - United States', 'y7eizhvZREOwp6%I5+nVRA': 'New York, NY - United States', 'dYjMvgSeS66eFLG9wcG5yA': 'New York, NY - United States', 'RjEwPGztTiC8Xzes7z2n7Q': 'New York, NY - United States', '3rcc7LpfQweV5e5c0am23g': 'New York, NY - United States', 'rs89vvEqTDCAanDW9r1A%w': 'New York, NY - United States', 'v+rbWUKuTIq2je1V0miS2w': 'New York, NY - United States', 'itnQLpBKSI6oY8H0Z3xuXw': 'New York, NY - United States', '4b61x9FCQoeYqSXK5cYgmw': 'New York, NY - United States', 'z6+sgAeqSkil8eoOWspU3w': 'New York, NY - United States', 'Is%u44KsTCqgBp0I0nUzgw': 'New York, NY - United States', 'tW52cXShQhWMUBS6cc+5zQ': 'New York, NY - United States', 'n7Zw3XRPT1WFlnDbau0uOw': 'New York, NY - United States', 'yxvVyJZuSZ+3gioYqnp+wQ': 'New York, NY - United States', '+dWH4Rs%T560LDGpMXT%Zg': 'New York, NY - United States', 'taw2Xc0eT7C9iCf0o5THCQ': 'New York, NY - United States', 'EPJB3TXsSDSO4ey50VqTzw': 'New York, NY - United States', '3v9AISuHRz69NQe71DL38A': 'New York, NY - United States', 'sOIxZPluQ7qtvoi1lWsJZg': 'New York, NY - United States', 'c5KCOyBNQ1+pblMu4zYl7w': 'New York, NY - United States', 'LY26eIi0TgKRyddTV6m7FA': 'Los Angeles, CA - United States', 'sS1xXlNcTuu1lz5IdSgfzA': 'New York, NY - United States', '75nG1YCjTpSIhbFFDs7Ssw': 'New York, NY - United States', 'kZ6jx2FbSweBlg77BbXJ1g': 'New York, NY - United States', 'BdT3n4ckQS+1UK14+z1NtA': 'New York, NY - United States', 'RlSFWGWWTl6pzHmZO2O7LA': 'New York, NY - United States', 'We+K2xFES%WUzs7TPoHPZQ': 'New York, NY - United States', 'XAAEr8drQDOtFueVhlKEtg': 'New York, NY - United States', 'v7tDRkIZQM27Fe0iZ0ZyLg': 'New York, NY - United States', 'KR%PMTVJTyek%XiZdae80w': 'New York, NY - United States', 'u14Bz2qLSsGjoAXrIm4eRg': 'Los Angeles, CA - United States', 'rxDmZ%OeREKr2gvOdTnOog': 'New York, NY - United States', 'sZzNAix7QcKc3JfyavsFtQ': 'New York, NY - United States', 'T9p+ePu0SKieeOpGRDKQ2g': 'New York, NY - United States', 'foqkd5EYTUStVOL2f+OVYQ': 'New York, NY - United States', 'MRD8jnmGQhK1glmEOBNDNg': 'New York, NY - United States', 'G%va1Le4ROSsQxqKGKhc+A': 'New York, NY - United States', 'kvJQHkpfQZG+7vc6tNYv4A': 'New York, NY - United States', 'lEUgq3R6TeCM1qFqTnJgdg': 'New York, NY - United States', 'syzpa38MTNWFkVgttYP0iw': 'New York, NY - United States', 'WPJdKiGxRrieMFso05+30A': 'New York, NY - United States', 'WhN%Kux8SlKHvyeC0%SHQw': 'New York, NY - United States', 'g+A6Il4+Qk+LiQgNbf4dQA': 'New York, NY - United States', 'hQrsOOQKQTSWUCXVOvMoEw': 'New York, NY - United States', 'bpup%m25TneguBS3Ilslfw': 'New York, NY - United States', 'hUzXcwExSy28sTPg7CcygQ': 'New York, NY - United States', 'Kk2DeVEjQNKALoKoh3FDIQ': 'New York, NY - United States', '5TM6NvE9RHKHdfAYYJMn0A': 'New York, NY - United States', 'ZChWQ90US76%XGFkuscYXA': 'New York, NY - United States', 'd9r1z%uLSlSzf%0byhmiWA': 'New York, NY - United States', 'ED08VaRyR%S7KFVjKGGDXw': 'New York, NY - United States', 'DJYo3hfvQEKPAhkk+chSEg': 'New York, NY - United States', 'BLv3ZKXnRR+xzlm4TGm4OQ': 'New York, NY - United States', '8U2NIJ8LSAuUAAWmOp8ELg': 'New York, NY - United States', 'DBsksqZrRRiPFNLgkIKCLg': 'New York, NY - United States', 'OUE2L440RDCDQCr2Lg4ZGA': 'New York, NY - United States', 'My2qEU4OTpecH%XezYcVuQ': 'New York, NY - United States', 'CgOFMPsgS4OcGBJpxddvrQ': 'New York, NY - United States', '4aLJyhpNQC+GHw7Cb58rwg': 'New York, NY - United States', '2riu8TXhR72DMmKVTqMhbg': 'New York, NY - United States', 'qKSTVZc7S3GAZHtj0U6uzQ': 'New York, NY - United States', 'NDZukFC9RgOCXSlgiWg%8w': 'New York, NY - United States', '1dW2v2axRdmV2I5q38L%5Q': 'New York, NY - United States', 'x1cgK466Rxq5E499OC4pHQ': 'Los Angeles, CA - United States', 'zNZIYW9mRQuyyty96LyDRg': 'New York, NY - United States', '%wwKCXRvRz69C2zS94%xtg': 'New York, NY - United States', 'H2bXlhyyTkOR4jdgA+0ecA': 'New York, NY - United States', '28hcoUj+Qhux8pqg8oRWsQ': 'New York, NY - United States', 'FHo4Ss6MSpyfr6sZkyh6HQ': 'New York, NY - United States', '%Om0ky4zQsOY1xM02uxrrg': 'New York, NY - United States', 'CmPh1ClAQ5uC0aW0tG2Zbg': 'New York, NY - United States', 'eTIxp7lNREuz0PlIvgVFIg': 'New York, NY - United States', 'TOM+qZKBQSaGxnRWXWFYfg': 'New York, NY - United States', 'Hw+0zmQrRiezg1XqJCzTag': 'Los Angeles, CA - United States', 'oLMCzjjmR5eBql2JjdlJjQ': 'New York, NY - United States', 'x9kAaRjJQR+HDdMvnfGfdw': 'New York, NY - United States', 'oh8PF78VQymYlOMiJYWf+w': 'New York, NY - United States', 'rdOi5s9nR0OJRzYfQUn4OA': 'New York, NY - United States', 'NJJHtz+ZSA+N2izDI9XBzA': 'New York, NY - United States', 'nK+DDUhzR7W65sKntTZmOg': 'New York, NY - United States', 'Rkt%aOv5T9KNZyZpLQE0fg': 'New York, NY - United States', 'E63TS+DiRjOuvX2rYiYHoA': 'New York, NY - United States', 'mnr6HQOCTIuyXRyIeZO3xA': 'New York, NY - United States', 'RdizV3rFTBORgXcD3VTrTg': 'New York, NY - United States', 'gLDU+D3ATAGFLbhAlikHfw': 'New York, NY - United States', 'gwHxn3kMTj66R4SIqHkVVA': 'New York, NY - United States', '25Bi81MMTuakFzy50olR6Q': 'New York, NY - United States', 'HQHeNTSVR1eGQanjdrYqQg': 'New York, NY - United States', 'Ppk+yTz%TmaATIGbgjraOA': 'New York, NY - United States', 'nFpF3XquRey0ES8wXfARFg': 'New York, NY - United States', 'YsigAx0yRl2B8ED+nTd%nQ': 'New York, NY - United States', '6fOV7QwlRFGTAHNKwZ1Uhw': 'New York, NY - United States', '9bSbh3r5TXKgDrJ%5O025A': 'New York, NY - United States', 'KWmpFSLvQO2MoXAudCFlAg': 'New York, NY - United States', 'LyHaAnuVQbOgEOewk46kuw': 'New York, NY - United States', 'PGQFChsAShW6FtY7VrTQOw': 'New York, NY - United States', '7+NNQE6GSyKhBb4jq+GhbA': 'New York, NY - United States', '3zelYhPdRFCp4dAijge3AQ': 'New York, NY - United States', 'kdXT4QDaS7GPXHKjTyNK7A': 'New York, NY - United States', '7hVeNtSJTBmTm%iDeyTsug': 'New York, NY - United States', 'Un4LFCTfSk6a+UNNMOnUFQ': 'Los Angeles, CA - United States', 'JzJAMSrVQ92eWSzL2t2Xxw': 'New York, NY - United States', 'EzsRZ5C0TXGuC+ty5VP76A': 'New York, NY - United States', 'lsp9N8R8RRizj9ibG8Pnbg': 'New York, NY - United States', 'Dy%+6yimTW+svvJns67PgA': 'Los Angeles, CA - United States', 'b09jGoTVRRyMsBrBVKG4GQ': 'Chicago, IL - United States', '4oBD23cuTp6hs4yyD4v5hA': 'Chicago, IL - United States', 'eT7ezrnJT2KLWfop3ZwmVw': 'Mexico City - Mexico', 'Oaw6y3nwSKmpBEnfVCUkOg': 'Los Angeles, CA - United States', '%BtH2x8WTIiD0XPVTsuTlQ': 'Los Angeles, CA - United States', 'QqjQtWn8RA69p8dRydClyg': 'Los Angeles, CA - United States', 'zI7rGbV8S5+d+kV+YcSPeA': 'Los Angeles, CA - United States', 'kWdQXEnHQn2VhR1%1oZeEg': 'Los Angeles, CA - United States', 'LUqa9KmOQ2WYXmoqZIPzmA': 'Los Angeles, CA - United States', '6xmfxt3SQ7iFZV4EIRq4Kw': 'Los Angeles, CA - United States', 'VwemA%clReug8NCRA0WagQ': 'Los Angeles, CA - United States', 'vbhpKCohQKyXCAPkXrMxNA': 'Los Angeles, CA - United States', 'chJ67OC+QQmmxDwYiLAHhg': 'Los Angeles, CA - United States'}


def main(database_path):
    entity_tree = {}
    photo_details = {}

    with sqlite3.connect(database_path) as db_connection:
        entity_tree = read_entities_with_parent(None, db_connection)
        photo_details = get_all_photo_details(db_connection)
    stack_details = get_stack_details(photo_details)

    start_photos_apple_script.run()

    album_conversion = create_entities_in_photos(entity_tree)
    import_photos(photo_details, album_conversion, stack_details)

    # print(json.dumps(entity_tree, indent=4))
    set_timezone('America/Denver')
    print('Done')


def rehash():
    start_photos_apple_script.run()
    cared_ids = set(try_again_timezone.keys())
    while len(cared_ids) > 0:
        found_id = press_keydown_until_find_photos(cared_ids)
        cared_ids.remove(found_id)
        rehash_single_photo(found_id)

    set_timezone('America/Denver')


def rehash_single_photo(photo_id):
    closest_city = try_again_timezone[photo_id]
    timezone = apple_closest_city_to_timezone[closest_city]
    set_timezone(timezone)
    date_time = get_photos_date_for_id_apple_script.run(photo_id)
    print('Rehashing photo {} to timezone {} and datetime {}'.format(photo_id, timezone, date_time))

    assign_photo_closest_city_and_date_time('Anchorage, AK - United States', date_time)
    assign_photo_closest_city_and_date_time(closest_city, date_time)


def get_stack_details(photo_details: dict) -> dict:
    stack_details = {}

    for photo_id in photo_details:
        photo_stack = photo_details[photo_id]['stack']
        if photo_stack is None:
            continue

        images_in_stack = stack_details.get(photo_stack)
        if images_in_stack is None:
            stack_details[photo_stack] = [photo_id]
        else:
            stack_details[photo_stack].append(photo_id)

    return stack_details


def read_entities_with_parent(parent: Optional[int], db_connection):
    entity_tree = {}

    parent_check = 'ISNULL' if parent is None else '= {}'.format(parent)

    entities_query = """SELECT id_local, name, creationId
                        FROM AgLibraryCollection
                        WHERE
                          parent {} AND
                          (creationId = 'com.adobe.ag.library.collection' OR
                              creationId = 'com.adobe.ag.library.group') AND
                          name != 'quick collection'""".format(parent_check)

    for (entity_id, entity_name, entity_type) in db_connection.execute(entities_query):
        # print('name={}, type={}'.format(entity_name, entity_type))
        if entity_type == 'com.adobe.ag.library.collection':
            entity_tree[entity_id] = {
                'type': entity_type,
                'name': entity_name
             }
        elif entity_type == 'com.adobe.ag.library.group':
            entity_tree[entity_id] = {
                'type': entity_type,
                'name': entity_name,
                'children': read_entities_with_parent(entity_id, db_connection)
            }

    return entity_tree


def create_entities_in_photos(entity_tree: dict) -> dict:
    return walk_entity_tree(entity_tree, None)


def walk_entity_tree(node, parent) -> dict:
    album_lightroom_to_photos_conversion = {}
    for key, item in node.items():
        if item['type'] == 'com.adobe.ag.library.group':
            create_folder_in_photos(item['name'], parent)
            sub_album_conversion = walk_entity_tree(item['children'], item['name'])
            album_lightroom_to_photos_conversion = {**album_lightroom_to_photos_conversion, **sub_album_conversion}
        else:
            item['photos_album_id'] = create_album_in_photos(item['name'], parent)
            album_lightroom_to_photos_conversion[key] = item['photos_album_id']

    return album_lightroom_to_photos_conversion


def create_folder_in_photos(name: str, parent_entity_name: Optional[str]):
    print('Creating folder {} in {}'.format(name, parent_entity_name))
    if parent_entity_name is None:
        create_folder_apple_script_root.run(name)
    else:
        create_folder_apple_script.run(name, parent_entity_name)


def create_album_in_photos(name: str, parent_entity_name: Optional[str]) -> str:
    print('Creating album {} in {}'.format(name, parent_entity_name))
    if parent_entity_name is None:
        result = create_album_apple_script_root.run(name)
        return result[applescript.AEType(b'seld')]
    else:
        result = create_album_apple_script.run(name, parent_entity_name)
        return result[applescript.AEType(b'seld')]


def get_all_photo_details(db_connection):
    photo_details = {}

    all_details_query = """SELECT Adobe_images.id_local as photo_id, Adobe_images.orientation as orientation, Adobe_images.rating as rating,
                                  AgHarvestedExifMetadata.gpsLatitude as latitude, AgHarvestedExifMetadata.gpsLongitude as longitude,
                                  AgLibraryRootFolder.absolutePath || AgLibraryFolder.pathFromRoot || AgLibraryFile.baseName || '.' || AgLibraryFile.extension as file,
                                  Adobe_AdditionalMetadata.xmp, Adobe_images.captureTime, Adobe_imageDevelopSettings.hasDevelopAdjustmentsEx as edits,
                                  AgLibraryFolderStackImage.stack as stack, Adobe_images.colorLabels as colorLabels
                           FROM Adobe_images
                           JOIN AgLibraryFile ON AgLibraryFile.id_local = Adobe_images.rootFile
                           JOIN AgHarvestedExifMetadata ON AgHarvestedExifMetadata.image = Adobe_images.id_local
                           JOIN AgLibraryFolder ON AgLibraryFolder.id_local = AgLibraryFile.folder
                           JOIN AgLibraryRootFolder ON AgLibraryRootFolder.id_local = AgLibraryFolder.rootFolder
                           JOIN Adobe_AdditionalMetadata ON Adobe_AdditionalMetadata.image = Adobe_images.id_local
                           JOIN Adobe_imageDevelopSettings ON Adobe_imageDevelopSettings.image = Adobe_images.id_local
                           LEFT JOIN AgLibraryFolderStackImage ON AgLibraryFolderStackImage.image = Adobe_images.id_local"""

    for (image_id, orientation, rating, latitude, longitude, file, xmp, date_time, edits, stack, colorLabels) in db_connection.execute(all_details_query):
        photo_details[image_id] = {
            'name': extract_name_from_xmp(xmp),
            'modified_date_time': date_time,
            'rating': rating,
            'orientation': orientation,
            'latitude': latitude,
            'longitude': longitude,
            'albums': get_associated_album_ids_for_picture(image_id, db_connection),
            'keywords': get_associated_keywords_for_picture(image_id, db_connection),
            'edits': True if edits == 1 else False,
            'stack': stack,
            'colorLabels': colorLabels,
            'file': file
        }
        # TODO: remove early break
        # if len(photo_details) > 5:
        #     break

    return photo_details


def extract_name_from_xmp(xmp: str) -> str:
    xml_tree = ElementTree.fromstring(xmp)
    xml_namespaces = {'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
                      'dc': 'http://purl.org/dc/elements/1.1/', 'x': 'adobe:ns:meta/'}

    return xml_tree.findtext('./rdf:RDF/rdf:Description/dc:title/rdf:Alt/rdf:li', namespaces=xml_namespaces)


def get_associated_album_ids_for_picture(picture_id: int, db_connection) -> List[int]:
    picture_collections_query = """SELECT AgLibraryCollectionImage.collection
                                   FROM Adobe_images
                                   JOIN AgLibraryCollectionImage ON Adobe_images.id_local = AgLibraryCollectionImage.image
                                   WHERE Adobe_images.id_local = ?"""

    return [album_id for (album_id,) in db_connection.execute(picture_collections_query, (picture_id,))]


def get_associated_keywords_for_picture(picture_id: int, db_connection) -> List[int]:
    picture_collections_query = """SELECT AgLibraryKeyword.name
                                   FROM AgLibraryKeywordImage
                                   JOIN AgLibraryKeyword ON AgLibraryKeyword.id_local == AgLibraryKeywordImage.tag
                                   WHERE AgLibraryKeywordImage.image = ?"""

    return [keyword for (keyword,) in db_connection.execute(picture_collections_query, (picture_id,)) if 'Aperture Stack ' not in keyword]


def import_photos(photo_details: dict, album_conversion: dict, stack_details: dict):
    time.sleep(5)
    for photo_id, photo_info in photo_details.items():
        if photo_paired_with_aperture_software_edits(photo_id, photo_info['stack'], stack_details, photo_details):
            print('Skipping import of {} because Aperture edits'.format(photo_id))
            continue  # skip this photo since we wanted the Aperture edited version
        modify_details_for_lightroom_edits(photo_id, photo_details)
        modify_details_for_edits(photo_id, photo_details, stack_details)
        generate_photo_metadata(photo_info)
        rotate_image(photo_info)
        set_timezone(photo_info.get('timezone', None))
        photos_photo_id = import_photo(photo_info['file'])
        photo_info['photos_id'] = photos_photo_id
        set_photo_metadata(photos_photo_id, photo_info)
        set_photo_timezone_through_photos(photos_photo_id, photo_info)
        add_photo_to_albums(photos_photo_id, photo_info['albums'], album_conversion)


def rotate_image(photo_info: dict):
    orientation_converter = {
        'AB': 1,
        'BC': 6,
        'CD': 3,
        'DA': 8
    }

    if photo_info['orientation'] is None or photo_info['exif_orientation'] is None:
        return

    lightroom_orientation = orientation_converter[photo_info['orientation']]
    exif_orientation = photo_info['exif_orientation']

    if lightroom_orientation != exif_orientation:
        print('Rotating to {}'.format(lightroom_orientation))
        photo_info['file'] = shutil.copy2(photo_info['file'], path.expanduser('~/Pictures/rotate/'))
        subprocess.run(['/usr/local/bin/exiftool', '-overwrite_original', '-orientation#={}'.format(lightroom_orientation), photo_info['file']])


def photo_paired_with_aperture_software_edits(photo_id: int, stack_id: int, stack_details: dict, photo_details: dict) -> bool:
    if stack_id is None:
        return False

    photos_in_stack: list = stack_details[stack_id]
    for other_photo_id in photos_in_stack:
        if other_photo_id == photo_id:
            continue  # don't check yourself
        if 'Aperture_preview' in photo_details[other_photo_id]['file']:
            return True

    return False


def find_sister_photo_associated_with_aperture_edits(photo_id: int, stack_id: int, stack_details: dict):
    if stack_id is None:
        return None

    photos_in_stack = stack_details[stack_id]

    for other_photo_id in photos_in_stack:
        if other_photo_id != photo_id:
            return other_photo_id

    return None


def modify_details_for_lightroom_edits(photo_id: int, photo_details: dict):
    photo_info = photo_details[photo_id]
    if photo_info['edits'] is True:
        base_name = path.splitext(path.basename(photo_info['file']))[0]
        new_path = path.join(lighroom_edits_folder, f'{base_name}.tif')
        photo_info['file'] = new_path


def modify_details_for_edits(photo_id: int, photo_details: dict, stack_details: dict):
    photo_info = photo_details[photo_id]
    stack_id = photo_info['stack']
    if 'Aperture_preview' in photo_info['file']:
        if photo_info['name'] is None:
            file_name = path.basename(photo_info['file'])
            file_name_no_aperture = file_name[:file_name.index('_Aperture_preview')]
            if file_name_no_aperture[:3] != 'IMG':
                photo_info['name'] = file_name_no_aperture

        sister_photo_id = find_sister_photo_associated_with_aperture_edits(photo_id, stack_id, stack_details)
        if sister_photo_id is not None:
            photo_info['albums'] += photo_details[sister_photo_id]['albums']


def set_timezone(timezone: str):
    if timezone is None:
        timezone = 'America/Denver'

    print('Setting timezone to {}'.format(timezone))
    subprocess.run(['sudo', '-S', '/usr/sbin/systemsetup', '-settimezone', timezone],
                   input=bytes('{}\n'.format(os.environ['SUDO_PSW']), 'utf-8'))
    time.sleep(1.0)


def import_photo(file_path) -> str:
    print('Importing {}'.format(file_path))
    result = import_photo_apple_script.run(file_path)
    return result[0][applescript.AEType(b'seld')]


def generate_photo_metadata(photo_info: dict):
    print('Generating metadata to {}: {}'.format(photo_info['name'], photo_info['file']))

    add_no_album_keyword(photo_info)
    add_edits_keyword(photo_info)
    add_needs_editing_keyword(photo_info)

    datetime_to_set, tag_to_add = determine_datetime(photo_info)

    photo_info['applescript_datetime'] = datetime_to_set

    if tag_to_add is not None:
        photo_info['keywords'].append(tag_to_add)


def set_photo_metadata(photos_photo_id: str, photo_info: dict):
    print('Setting metadata to {} ({}): {}'.format(photos_photo_id, photo_info['name'], photo_info['file']))

    set_metadata_apple_script.run(photos_photo_id, photo_info['name'], photo_info['applescript_datetime'], photo_info['rating'], photo_info['latitude'], photo_info['longitude'], photo_info['keywords'])


def press_keydown_until_find_photos(photo_ids: set):
    selected_id = None
    while selected_id not in photo_ids:
        go_down_selection_photos_apple_script.run()
        time.sleep(1.0)
        applescript_result = get_photos_selection_apple_script.run()
        if len(applescript_result) > 0:
            selected_id = applescript_result[0][applescript.AEType(b'seld')]
            print(selected_id)

    return selected_id


def assign_photo_closest_city_and_date_time(closest_city: str, date_time: datetime.datetime):
    set_timezone('Pacific/Midway')  # I need to be in a different timezone than the photo I am editing for the setting to take effect, stupid Photos

    month = date_time.strftime('%m')
    day = date_time.strftime('%d')
    year = date_time.strftime('%Y')
    hour = date_time.strftime('%I')
    minute = date_time.strftime('%M')
    second = date_time.strftime('%S')
    meridiem = date_time.strftime('%p')[0]

    print('Setting closest city to {}...'.format(closest_city))

    change_timezone_photos_apple_script.run(closest_city, month, day, year, hour, minute, second, meridiem)


def set_photo_timezone_through_photos(photos_photo_id: str, photo_info: dict):
    selected_id = None
    while selected_id != photos_photo_id:
        go_down_selection_photos_apple_script.run()
        time.sleep(1.0)
        applescript_result = get_photos_selection_apple_script.run()
        if len(applescript_result) > 0:
            selected_id = applescript_result[0][applescript.AEType(b'seld')]
            print(selected_id)

    date_time: datetime.datetime = photo_info['datetime_photos']
    if photo_info.get('timezone', None) is None or date_time is None:
        return

    closest_city = timezone_to_apple_closest_city[photo_info['timezone']]
    assign_photo_closest_city_and_date_time(closest_city, date_time)


def add_no_album_keyword(photo_info: dict):
    if len(photo_info['albums']) == 0:
        photo_info['keywords'].append('no album')


def add_edits_keyword(photo_info: dict):
    if photo_info['edits'] is True:
        # photo_info['keywords'].append('edits')
        pass


def add_needs_editing_keyword(photo_info: dict):
    if photo_info['colorLabels'] == 'Yellow':
        photo_info['keywords'].append('needs editing')


# imageTimeZoneName
# fileName = 'IMG_9163.CR2'
# Europe/Zurich
# America/New_York
# America/Chicago
# America/Denver
# America/Los_Angeles
# Photos time is offset from January 1, 2001 00:00:00 UTC.
# uuid is what is returned from AppleScript after import
# imageTimeZoneName is one of the above timezone names, etc.  Or a GMT-0600 string.
# imageTimeZoneOffsetSeconds is the number of seconds from UTC the resulting timezone is in, and takes into account DST
# imageDate is the number of seconds from 2001 to timezone aware time, probably accounts for DST.  When changing the timezone, I'll need to adjust this field
# createDate is the number of seconds from 2001 to when the photo was imported into Photos, but it isn't timezone aware, just take the UTC time to mean my time.  We don't need to do anything with this field.
def determine_datetime(photo_info: dict) -> Tuple[Optional[str], Optional[str]]:
    datetime_from_db_str = photo_info['modified_date_time']
    file_path = photo_info['file']
    latitude = photo_info['latitude']
    longitude = photo_info['longitude']
    keywords = photo_info['keywords']

    with open(file_path, 'rb') as image_file:
        exif_tags = exifread.process_file(image_file, details=False)

    try:
        photo_info['exif_orientation'] = exif_tags['Image Orientation'].values[0]
    except KeyError:
        photo_info['exif_orientation'] = None

    try:
        datetime_from_exif_str = exif_tags['EXIF DateTimeOriginal'].values
    except KeyError:
        datetime_from_exif_str = None

    db_datetime = datetime_from_db(datetime_from_db_str)
    exif_datetime = datetime_from_exif(datetime_from_exif_str)

    datetime_to_set = None
    tag_to_add = None

    if 'GPS GPSTimeStamp' not in exif_tags or 'GPS GPSDate' not in exif_tags or file_path[-3:] == 'CR2' or file_path[-3:] == 'cr2':
        tag_to_add = 'timezone suspect'
        print('Timezone is suspect')
        timezone_keyword = extract_timezone_from_keywords(keywords)
        if timezone_keyword is not None:
            print('...but tz in keywords {}'.format(timezone_keyword))
            photo_info['timezone'] = timezone_keyword
            tag_to_add = None
        elif latitude is not None and longitude is not None:
            timezone = tf.timezone_at(lat=latitude, lng=longitude)
            print('...but looking up lat/long tz is {}'.format(timezone))
            photo_info['timezone'] = timezone
            tag_to_add = None
        gps_time = False
    else:
        gps_time = True

    # Determine if they are equal, if they are, return None since we just want Photos to use what is built into the photo
    if db_datetime == exif_datetime:
        datetime_to_set = None
        photo_info['datetime_photos'] = exif_datetime
    elif db_datetime is None:
        datetime_to_set = None
        photo_info['datetime_photos'] = exif_datetime
    else:
        # not equal!  Go check to see if this photo has GPS coordinates built in.
        print('Times are not equal!')
        if gps_time:
            # there are coordinates, don't change the time because Photos will screw it up!
            print('But there is GPS time')
            datetime_to_set = None
            photo_info['datetime_photos'] = exif_datetime
            tag_to_add = 'gps with bad time'
        else:
            datetime_to_set = convert_datetime_to_applescript(db_datetime)
            photo_info['datetime_photos'] = db_datetime

    return (datetime_to_set, tag_to_add)


def extract_timezone_from_keywords(keywords: list) -> Optional[str]:
    timezone_keywords = [keyword for keyword in keywords if keyword[:3] == 'tz-']
    if len(timezone_keywords) > 1:
        print('Multiple timezone keywords!')
        return None
    elif len(timezone_keywords) == 0:
        return None
    else:
        keywords.remove(timezone_keywords[0])
        return timezone_keywords[0][3:]


def datetime_from_db(datetime_str: str) -> Optional[datetime.datetime]:
    if datetime_str is None:
        return None

    date_time = None

    if len(datetime_str) == 10:
        date_time = datetime.datetime.strptime(datetime_str, '%Y-%m-%d')
    elif len(datetime_str) == 16:
        date_time = datetime.datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M')
    else:
        date_time = datetime.datetime.strptime(datetime_str[0:19], '%Y-%m-%dT%H:%M:%S')

    return date_time


def datetime_from_exif(datetime_str: str) -> Optional[datetime.datetime]:
    if datetime_str is None:
        return None
    try:
        exif_datetime = datetime.datetime.strptime(datetime_str, '%Y:%m:%d %H:%M:%S')
    except ValueError:
        exif_datetime = None

    return exif_datetime


def convert_datetime_to_applescript(date_time: datetime.datetime) -> Optional[str]:
    if date_time is None:
        return None

    # 0:*:* AM converts into 12 AM, but 12:*:* AM also converts to 12 AM.  So, use PM if 12 is specified to make 12 PM
    meridiem = 'PM' if date_time.hour == 12 else 'AM'

    return date_time.strftime('%m-%d-%Y %H:%M:%S {}'.format(meridiem))


def add_photo_to_albums(photos_photo_id: str, lightroom_album_ids: List[int], album_conversion: dict):
    print('Adding photo to album(s) {}'.format(lightroom_album_ids))
    for lightroom_album_id in lightroom_album_ids:
        try:
            assign_album_apple_script.run(photos_photo_id, album_conversion[lightroom_album_id])
        except KeyError:
            pass  # a photo was slated to go into an album that I decided not to move over, like a slideshow "album"


if __name__ == '__main__':
    database_path = sys.argv[1]
    print('Transitioning {}'.format(database_path))
    main(database_path)
    # rehash()
