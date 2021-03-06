from flask import Flask
from flask import render_template
from flask import request

from awscommon import *

import base64
import traceback
import tempfile
import time
import random
import boto3

application = Flask(__name__)

DISABLE_UPLOADING=False

class Image:
    def __init__ (self, s3key, title, tags):
        self.s3key = s3key
        self.title = title
        self.tags = tags

def is_image (key):  # TODO: trivial check to be improved
    return key.lower().endswith(('jpg','png','jpeg','tiff','svg'))

def get_all_images(limit = None):
    bucket = get_s3_bucket()

    images = []
    for obj in bucket.objects.all():
        if limit != None and len(images) == limit:
            break
        if not is_image(obj.key):
            continue
        if obj.key.startswith("pending"):
            continue

        title=""
        tags=[]

        try:
            table = get_dynamo_table()
            response = table.get_item(
               Key={
                    'imageid': obj.key,
                }
            )

            item = response['Item']
            title = item["title"]
            tags = item["tags"]
        except:
            pass

        images.append(Image(obj.key, title, tags)) 

    return images


@application.route('/newpost', methods=['GET', 'POST'])
def upload_image():

    if request.method == "POST":
        if request.files:
            image = request.files["image"]
            if not is_image(image.filename):
                return render_template('newpost.html', msg='File not valid!')

            title = ""
            tags = []

            if "title" in request.form:
                _title = request.form["title"]
                if _title != None:
                    title = _title
            if "tags" in request.form:
                _tags = request.form["tags"]
                if _tags != None:
                    tags = [t.strip() for t in _tags.split(",")]
            if len(tags) < 1:
                tags.append("~") # workaround: DynamoDB does not accept empty strings


            with tempfile.NamedTemporaryFile() as tempf:
                image.save(tempf.name)

                bucket = get_s3_bucket()

                # Construct a key
                key = ""
                if request.environ['REMOTE_ADDR'] is not None:
                    key = request.environ['REMOTE_ADDR']
                key = key + str(time.time()) + image.filename

                print("Uploading: {}".format(key))

                try:
                    if DISABLE_UPLOADING == False:
                        bucket.upload_file(tempf.name, "pending/" + key)

                    # Send a message to SQS
                    filtername = "(None)"
                    if "filter" in request.form:
                        filtername = request.form["filter"]

                    queue = get_sqs_queue()
                    msgstring = "{}\n{}".format(key, filtername)
                    msg = base64.b64encode(bytes(msgstring, 'ascii'))
                    queue.send_message(MessageBody=msg.decode('ascii'))

                    # Save metadata
                    table = get_dynamo_table()
                    table.put_item(
                       Item={
                            'imageid': key,
                            'title': title,
                            'tags': tags
                        }
                    )
                except:
                    traceback.print_exc()

            return render_template('newpost.html', msg="Image uploaded!")

    return render_template('newpost.html', msg='')

@application.route('/')
def home():
    # list images to be displayed
    all_images = get_all_images(25)
    
    images = [[], [], []]
    column_index = 0
    for img in all_images:
        imgpath = get_s3_fullpath(img.s3key)
        if len(img.tags) != 0:
            tagsstring = "[{}]".format(",".join(img.tags))
        else:
            tagsstring = ""

        images[column_index].append((imgpath, img.title, tagsstring))
        column_index = (column_index + 1) % 3

    return render_template('home.html', images1=images[0], images2=images[1], images3=images[2])

if __name__ == "__main__":
    applicationp.run()
