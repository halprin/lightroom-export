# https://github.com/philroche/py-lightroom-export
# https://github.com/patrikhson/photo-export
# https://photo.stackexchange.com/questions/93172/where-can-i-find-lightroom-database-documentation
# https://macosxautomation.com/applescript/imageevents/index.html
# https://discussions.apple.com/thread/6874314

# com.adobe.ag.library.group = folder
# com.adobe.ag.library.collection = album
# 37 top level things

# Todo:
# - make aperture edited files show up in the original file's album
# - when a photo is edited in Lightroom, export it it in the highest quality way possible with all the metadata, and import that photo instead
# - Get the rotation correct
# - Make it so any changes written to the Photos database are not lost when recovering the db.

import sqlite3
from typing import Optional, List, Tuple
import json
import applescript
from xml.etree import ElementTree
import datetime
import exifread
from os import path
import os
import sys
from timezonefinder import TimezoneFinder
import pendulum
import time
import subprocess


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


def main(database_path):
    entity_tree = {}
    photo_details = {}

    with sqlite3.connect(database_path) as db_connection:
        entity_tree = read_entities_with_parent(None, db_connection)
        photo_details = get_all_photo_details(db_connection)
    stack_details = get_stack_details(photo_details)
    # print(json.dumps(stack_details, indent=4))

    start_photos_apple_script.run()

    album_conversion = create_entities_in_photos(entity_tree)
    import_photos(photo_details, album_conversion, stack_details)

    # modify_photos_database(photos_library_path, photo_details)
    # print(json.dumps(entity_tree, indent=4))
    set_timezone('America/Denver')
    print('Done')


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

    all_details_query = """SELECT Adobe_images.id_local as photo_id, Adobe_images.rating as rating,
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

    for (image_id, rating, latitude, longitude, file, xmp, date_time, edits, stack, colorLabels) in db_connection.execute(all_details_query):
        photo_details[image_id] = {
            'name': extract_name_from_xmp(xmp),
            'modified_date_time': date_time,
            'rating': rating,
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
        # if len(photo_details) > 100:
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

    return [keyword for (keyword,) in db_connection.execute(picture_collections_query, (picture_id,))]


def import_photos(photo_details: dict, album_conversion: dict, stack_details: dict):
    for photo_id, photo_info in photo_details.items():
        if photo_paired_with_aperture_software_edits(photo_id, photo_info['stack'], stack_details, photo_details):
            print('Skipping import of {} because Aperture edits'.format(photo_id))
            continue  # skip this photo since we wanted the Aperture edited version
        modify_details_for_edits(photo_id, photo_details, stack_details)
        generate_photo_metadata(photo_info)
        set_timezone(photo_info.get('timezone', None))
        photos_photo_id = import_photo(photo_info['file'])
        photo_info['photos_id'] = photos_photo_id
        set_photo_metadata(photos_photo_id, photo_info)
        add_photo_to_albums(photos_photo_id, photo_info['albums'], album_conversion)


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


def add_no_album_keyword(photo_info: dict):
    if len(photo_info['albums']) == 0:
        photo_info['keywords'].append('no album')


def add_edits_keyword(photo_info: dict):
    if photo_info['edits'] is True:
        photo_info['keywords'].append('edits')


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
            tag_to_add = 'timezone edited'
        elif latitude is not None and longitude is not None:
            timezone = tf.timezone_at(lat=latitude, lng=longitude)
            print('...but looking up lat/long tz is {}'.format(timezone))
            photo_info['timezone'] = timezone
            tag_to_add = 'timezone edited'
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


def modify_photos_database(photos_library_path: str, photo_details: dict):
    time.sleep(20.0)
    print('Quitting Photos')
    quit_photos_apple_script.run()

    input("Press return to continue to edit the Photos' database")

    print("Starting edit of Photos' database")

    photos_database_path = '{}/database/photos.db'.format(photos_library_path)
    write_time_data_into_version_query = """UPDATE RKVersion
                                               SET imageDate = ?,
                                                   imageTimeZoneOffsetSeconds = ?,
                                                   imageTimeZoneName = ?
                                               WHERE uuid = ?"""

    # mountain_timezone = pendulum.timezone('America/Denver')
    # utc_timezone = pendulum.timezone('UTC')
    utc_2001 = pendulum.datetime(2001, 1, 1, 0, 0, 0, tz='UTC')

    with sqlite3.connect(photos_database_path) as photo_db_connection:
        for photo_key in photo_details:
            photo_info = photo_details[photo_key]

            if 'timezone' not in photo_info:
                continue

            photos_id = photo_info['photos_id']
            timezone_str = photo_info['timezone']
            photo_datetime = photo_info['datetime_photos']

            if not isinstance(photo_datetime, datetime.datetime):
                print("id {} doesn't have a proper datetime!  date={}, date type={}".format(photos_id, photo_datetime, type(photo_datetime)))
                print('Not setting timezone after all')
                continue

            timezone = pendulum.timezone(timezone_str)
            photo_datetime_with_timezone = pendulum.instance(photo_datetime, timezone)

            new_image_date_period = photo_datetime_with_timezone - utc_2001
            new_image_creation = new_image_date_period.in_seconds()

            # utc_offset = timezone.utcoffset(photo_datetime)
            timezone_delta = photo_datetime_with_timezone.offset

            print('name={}, id={}, timezone={}, timezone_delta={}, date={}'.format(photo_info['name'], photos_id, timezone_str, timezone_delta, new_image_creation))

            photo_db_connection.execute(write_time_data_into_version_query, (new_image_creation, timezone_delta, timezone_str, photos_id))


if __name__ == '__main__':
    database_path = sys.argv[1]
    print('Transitioning {}'.format(database_path))
    main(database_path)
