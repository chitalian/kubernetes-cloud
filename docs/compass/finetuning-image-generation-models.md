---
description: >-
  Learn about using Argo Workflows for finetuning and training Stable Diffusion
  models.
---

# Finetuning Image Generation Models

Finetuning and training Stable Diffusion can be computationally expensive. CoreWeave Cloud allows for the training of Stable Diffusion models using on-demand compute resources along with the infrastructure to support it. While this demo barely scratches the surface of finetuning, the following example is a good place to get started.

This guide is intended to be a reference example of [how to use Argo Workflows](broken-reference) to set up a pipeline on CoreWeave for finetuning and training Stable Diffusion models. While the following barely scratches the surface of finetuning, it should be enough to get you started.

The reference example uses the [Hugging Face Diffusers](https://github.com/huggingface/diffusers/) library for finetuning and saving Stable Diffusion models.

{% hint style="info" %}
**Note**

This reference example is not intended to be a production application; rather, it is a demo for utilizing CoreWeave resources to set up a pipeline.
{% endhint %}

The base model being trained on can be provided directly in a [PVC (PersistentVolumeClaim)](broken-reference), or in a Stable Diffusion model identifier from [Hugging Face's model repository](https://huggingface.co/models). The dataset trained upon needs to be in the same PVC in text and image format.

Presently, the reference example uses the following container configuration to train models on:

* 8 vCPU (AMD EPYC, usually)
* 32GB RAM
* NVIDIA A40/A6000 GPUs (48GB VRAM)

The above configuration has been found to be optimal for training Stable Diffusion models. However, you can use any configuration you wish, as long as it meets the minimum requirements for training Stable Diffusion models. The above configuration is billed at $1.52 per hour through CoreWeave's [resource based pricing](../../resources/resource-based-pricing.md) model.

There is an optional test [Inference endpoint](examples/pytorch-hugging-face-diffusers-stable-diffusion-text-to-image.md) that can be enabled and deployed automatically when the model completes finetuning. This Inference container defaults to the following configuration:

* 4 vCPU
* 8GB RAM
* NVIDIA Quadro RTX 5000 (16GB VRAM)

The above configuration for inferencing Stable Diffusion is billed at $0.65 per hour through CoreWeave's [resource based pricing](../../resources/resource-based-pricing.md) model.

{% embed url="https://github.com/coreweave/kubernetes-cloud/tree/amercurio/sd-finetuner/sd-finetuner-workflow" %}
View the code on GitHub
{% endembed %}

## Setup

{% hint style="info" %}
**Note**

This guide assumes that you have already followed the process to set up the CoreWeave Kubernetes environment. If you have not done so already, follow our [Getting Started Guide](../../coreweave-kubernetes/getting-started.md) before proceeding with this guide.
{% endhint %}

The following Kubernetes-based components are required:

### [Argo Workflows](broken-reference)

You can deploy Argo Workflows using the [Application Catalog](https://apps.coreweave.com/). From the application deployment menu, click on the **Catalog** tab, then search for `argo-workflows` to find and deploy the application.

<figure><img src="../.gitbook/assets/argos.png" alt=""><figcaption><p>Argo Workflows</p></figcaption></figure>

### [PVC](broken-reference)

Create a `ReadWriteMany` PVC storage volume from the [Storage](broken-reference) menu.

`1TB` to `2TB` is recommended for training Stable Diffusion models, depending on the size of the dataset and how many finetunes you wish to run. These PVCs can be shared between multiple finetune runs. We recommend using HDD type storage, as the finetuner does not require high random I/O performance.

<figure><img src="../.gitbook/assets/pvc.png" alt=""><figcaption><p>Configuring a PVC storage volume from the Cloud UI</p></figcaption></figure>

{% hint style="info" %}
**Note**

It is easy to [increase the size](broken-reference) of a PVC as needed.
{% endhint %}

This workflow expects a default PVC name of `sd-finetune-data`. This name can be changed once you are more comfortable with the workflow and configure it. If you prefer, the PVC can also be deployed using the YAML snippet below, applied using `kubectl apply -f`:

{% code title="sd-finetune-pvc.yaml" %}
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: sd-finetune-data
spec:
  storageClassName: shared-hdd-ord1
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 2000Gi
```
{% endcode %}

### Optional Components

The following components are optional, but may make your interaction easier:

#### filebrowser

This application allows you to share out and access your PVC using an easy application that lets you upload and download files and folders. You can find and deploy the filebrowser over at the same [Application Catalog](https://apps.coreweave.com/) that you used to deploy Argo Workflows.

It is recommended that the name you give the filebrowser application be very short, or you will run into SSL CNAME issues. We recommend using the name `finetune`.

Simply select the `sd-finetune-data` PVC that you created earlier. **Make sure that you actually add your PVC to the filebrowser list of mounts!**

{% hint style="success" %}
**Tip**

Some people may prefer to use a Virtual Server to interact with their `PVC` via ssh or some other mechanism. This flexibility is one of the key advantages of CoreWeave.
{% endhint %}

<figure><img src="../.gitbook/assets/filebrowser.png" alt=""><figcaption><p>The filebrowser application</p></figcaption></figure>

## Dataset Setup

At this point, you should have a PVC set up that is accessible via the filebrowser application or some other mechanism. For each dataset you want to use, create a directory with a meaningful name such as `dataset`.

The data will be text-image pairs, where each pair has the same filename. The caption files must have the `.txt` file extension, whereas the supported file extensions for images are `.png`, `.jpg`, `.jpeg`, `.bmp`, and `.webp`.

#### Example

Below we have a dataset in the directory named `dataset`, with six text-image pairs. Each image has its corresponding caption in a `.txt` file with the same filename as the image file.

<figure><img src="../.gitbook/assets/dataset-example.png" alt=""><figcaption><p>A dataset with text-image pairs</p></figcaption></figure>

## Permissions Setup

In order to automatically create an `InferenceService`, the Argo Workflow job needs special permissions. The YAML snippet below exemplifies a `ServiceAccount` with the required permissions.

To follow along, copy the snippet below into a file titled `inference-role.yaml`:

{% code title="inference-role.yaml" %}
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: inference
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: role:inference
rules:
  - apiGroups:
      - serving.kubeflow.org
    resources:
      - inferenceservices
    verbs:
      - '*'
  - apiGroups:
      - serving.knative.dev
    resources:
      - services
      - revisions
    verbs:
      - '*'
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: rolebinding:inference-inference
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: role:inference
subjects:
  - kind: ServiceAccount
    name: inference
```
{% endcode %}

Invoking `kubectl apply -f inference-role.yaml` will apply the permissions described above.

## Getting and Running the Workflow

To follow along, pull the latest version of [the demo code](https://github.com/coreweave/kubernetes-cloud/tree/amercurio/sd-finetuner/sd-finetuner-workflow).

This repository includes the following files:

| Filename                        | Description                                                                                                |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `sd-finetune-workflow.yaml`     | The Argo Workflow itself                                                                                   |
| `inference-role.yaml`           | The inference role you configured earlier in this demo                                                     |
| `sd-finetune-pvc.yaml`          | A model storage volume, as described earlier in this demo                                                  |
| `sd-finetuner/Dockerfile`       | A Dockerfile that can be used to build your own finetuner image, should you modify the `finetuner.py` code |
| `sd-finetuner/finetuner.py`     | The simple reference example for finetuning Stable Diffusion                                               |
| `sd-finetuner/requirements.txt` | The Python requirements which list the dependencies for the finetuner                                      |

For reference, a copy of the `sd-finetune-workflow.yaml` is featured at the bottom of this document, but the GitHub repository has the authoritative version.

Assuming that you now have a copy of `sd-finetune-workflow.yaml`, the Argo Workflows may be invoked using `argo submit` command with the following options:

```shell-session
$ argo submit sd-finetune-workflow.yaml \
        -p run_name=example-sd \
        -p model=CompVis/stable-diffusion-v1-4 \
        -p dataset=dataset \
        -p hf_token=<Add your HuggingFace token here> \
        -p wandb_token=<Add your WandB token here> \
        -p run_inference=true
        --serviceaccount inference
```

{% hint style="info" %}
**Note**

The results of this exercise should output to a folder in your PVC under `finetunes/<run_name>`.
{% endhint %}

The parameters included in the above are:

| Parameter Name               | Description                                                                                                                                                                                                                                                                              |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `run_name`                   | It is strongly recommended that the value of this parameter be unique, as it is what is used to name the `InferenceService` and for tracking the finetune through [WandB](https://wandb.ai/). Consequently, the `run_name` must meet DNS standards. Keep this parameter short in length. |
| `model`                      | This example uses a Hugging Face model identifier to pull down Stable Diffusion 1.4 for finetuning. This model will be cached on subsequent runs on your PVC, under `models`.                                                                                                            |
| `dataset`                    | The name of the directory on the PVC.                                                                                                                                                                                                                                                    |
| `hf_token`                   | Your Hugging Face token for pulling private models, such as Stable Diffusion 1.4                                                                                                                                                                                                         |
| `wandb_token`                | Your [WandB token](https://wandb.ai/authorize) for tracking the finetune run.                                                                                                                                                                                                            |
| `run_inference`              | This parameter explicitly tells the Workflow that we want to run a test inference service when this exercise is done. It is not intended to be a production service, but to provide an end-to-end demonstration, allowing you to test the finetuned model.                               |
| `--serviceaccount inference` | Required for `run_inference` to work correctly.                                                                                                                                                                                                                                          |

{% hint style="info" %}
**Note**

Other methods of passing parameters to your jobs may be preferred to inline definitions. These methods include:

* An [Argo parameters file](https://argoproj.github.io/argo-workflows/walk-through/parameters/) applied using `argo submit -f,` or the `-p` option may be used to configure additional customizations.
* Templating using [Helm Charts](https://helm.sh/).
* Programmatically using the [Argo Workflows API](https://argoproj.github.io/argo-workflows/swagger/).
* Using the [Argo Web UI](https://docs.coreweave.com/compass/finetuning-machine-learning-models#argo-workflows).
{% endhint %}

Once the job is submitted, you should see output that looks very much like the following:

```
Name:                sd-finetune-qn92w
Namespace:           tenant-sta-amercurio-amercurio
ServiceAccount:      inference
Status:              Pending
Created:             Mon Oct 24 16:41:29 -0700 (1 second ago)
Progress:            
Parameters:          
  run_name:          test
  model:             CompVis/stable-diffusion-v1-4
  dataset:           dataset
  batch_size:        1
  hf_token:          <A Hugging Face key here>
  run_inference:     True
  inference_only:    False
  wandb_api_key:     <A wandb API key here>
  pvc:               sd-finetune-data
  lr:                5e-6
  epochs:            10
  use_ema:           False
  ucg:               0.1
  gradient_checkpointing: False
  use_8bit_adam:     False
  adam_beta1:        0.9
  adam_beta2:        0.999
  adam_weight_decay: 1e-2
  adam_epsilon:      1e-8
  seed:              42
  save_steps:        500
  resolution:        512
  resize:            False
  center_crop:       False
  resize_interp:     lanczos
  shuffle:           True
  image_log_steps:   500
  image_log_amount:  4
  project_id:        sd-finetune
  region:            ORD1
  trainer_gpu:       RTX_A6000
  inference_gpu:     Quadro_RTX_5000
  downloader_image:  ghcr.io/wbrown/gpt_bpe/model_downloader
  downloader_tag:    797b903
  finetuner_image:   docker.io/harubaru1/sd-finetuner
  finetuner_tag:     r6
  inference_image:   docker.io/harubaru1/stable-diffusion
  inference_tag:     5
```

## Observing the Argo Workflow

At this point, we can observe the job via several mechanisms, now that we have the `Name` of `sd-finetune-qn92w`:

### Argo Commands

#### `argo watch`

Invoking `argo watch sd-finetune-qn92w` tells Argo that we want to watch the job as it goes through the stages of:

* `model-download`
* `model-finetune`\
  and
* `model-inference`

#### Example output

```
Name:                sd-finetune-qn92w
Namespace:           tenant-sta-amercurio-amercurio
ServiceAccount:      inference
Status:              Running
Conditions:          
 PodRunning          True
Created:             Mon Oct 24 16:41:29 -0700 (4 minutes ago)
Started:             Mon Oct 24 16:41:30 -0700 (4 minutes ago)
Duration:            4 minutes 19 seconds
Progress:            1/2
ResourcesDuration:   21s*(1 cpu),1m52s*(100Mi memory)
Parameters:          
  run_name:          test
  model:             CompVis/stable-diffusion-v1-4
  dataset:           dataset
  batch_size:        1
  hf_token:          <A Hugging Face key here>
  run_inference:     True
  inference_only:    False
  wandb_api_key:     <A wandb API key here>
  pvc:               sd-finetune-data
  lr:                5e-6
  epochs:            10
  use_ema:           False
  ucg:               0.1
  gradient_checkpointing: False
  use_8bit_adam:     False
  adam_beta1:        0.9
  adam_beta2:        0.999
  adam_weight_decay: 1e-2
  adam_epsilon:      1e-8
  seed:              42
  save_steps:        500
  resolution:        512
  resize:            False
  center_crop:       False
  resize_interp:     lanczos
  shuffle:           True
  image_log_steps:   500
  image_log_amount:  4
  project_id:        sd-finetune
  region:            ORD1
  trainer_gpu:       RTX_A6000
  inference_gpu:     Quadro_RTX_5000
  downloader_image:  ghcr.io/wbrown/gpt_bpe/model_downloader
  downloader_tag:    797b903
  finetuner_image:   docker.io/harubaru1/sd-finetuner
  finetuner_tag:     r6
  inference_image:   docker.io/harubaru1/stable-diffusion
  inference_tag:     5

STEP                  TEMPLATE          PODNAME                       DURATION  MESSAGE
 ● sd-finetune-qn92w  main                                                        
 ├───✔ downloader(0)  model-downloader  sd-finetune-qn92w-3584625971  15s         
 └───● finetuner      model-finetuner   sd-finetune-qn92w-420816036   3m 
```

#### `argo logs`

Invoking `argo logs -f sd-finetune-qn92w kfserving-container` watches the logs in real time.

{% hint style="warning" %}
**Important**

If this process appears to hang while outputting the message `Loading the model`, this is due to a bug in the terminal display code which is exposed during initial model download and caching. To fix this, kill the relevant pod or job, then resubmit it. This should result in the proper progress display.
{% endhint %}

#### Example Output

```
sd-finetune-qn92w-420816036: wandb: Currently logged in as: haruu. Use `wandb login --relogin` to force relogin
sd-finetune-qn92w-420816036: wandb: WARNING Path /sd-finetune-data/finetunes/test/wandb/wandb/ wasn't writable, using system temp directory.
sd-finetune-qn92w-420816036: wandb: WARNING Path /sd-finetune-data/finetunes/test/wandb/wandb/ wasn't writable, using system temp directory
sd-finetune-qn92w-420816036: wandb: Tracking run with wandb version 0.13.4
sd-finetune-qn92w-420816036: wandb: Run data is saved locally in /tmp/wandb/run-20221024_234339-lfrc5t20
sd-finetune-qn92w-420816036: wandb: Run `wandb offline` to turn off syncing.
sd-finetune-qn92w-420816036: wandb: Syncing run test
sd-finetune-qn92w-420816036: wandb: ⭐️ View project at https://wandb.ai/haruu/sd-finetune
sd-finetune-qn92w-420816036: wandb: 🚀 View run at https://wandb.ai/haruu/sd-finetune/runs/lfrc5t20
sd-finetune-qn92w-420816036: RUN_NAME: test
sd-finetune-qn92w-420816036: HOST: sd-finetune-qn92w-420816036
sd-finetune-qn92w-420816036: CUDA: 11.6
sd-finetune-qn92w-420816036: TORCH: 1.12.1+cu116
sd-finetune-qn92w-420816036: TRANSFORMERS: 4.23.1
sd-finetune-qn92w-420816036: DIFFUSERS: 0.5.1
sd-finetune-qn92w-420816036: MODEL: /sd-finetune-data/models/CompVis/stable-diffusion-v1-4
sd-finetune-qn92w-420816036: FP16: False
sd-finetune-qn92w-420816036: RESOLUTION: 512
sd-finetune-qn92w-420816036: DEVICE: cuda
sd-finetune-qn92w-420816036: RANDOM SEED: 42
...
100% 51/51 [00:07<00:00,  7.00it/s]
Downloading: 100% 4.55k/4.55k [00:00<00:00, 4.42MB/s]
Downloading: 100% 1.22G/1.22G [00:13<00:00, 93.4MB/s]
sd-finetune-qn92w-420816036: CPU: (maxrss: 8,008mb F: 86,588mb) GPU: (U: 17,890mb F: 33,636mb T: 51,527mb) TORCH: (R: 15,466mb/16,148mb, A: 12,957mb/15,320mb)
sd-finetune-qn92w-420816036: Done!
wandb: Waiting for W&B process to finish... (success).                         
sd-finetune-qn92w-420816036: wandb: 
sd-finetune-qn92w-420816036: wandb: Run history:
sd-finetune-qn92w-420816036: wandb: epoch ▁▁▁▁▂▂▂▂▃▃▃▃▃▃▃▃▄▄▄▄▅▅▅▅▆▆▆▆▆▆▆▆▇▇▇▇████
sd-finetune-qn92w-420816036: wandb:  loss █▁▁▁▁▃▄▂▄▅▁▂▁▁▁▂▁▁▁▂▃▃▃▁▃▁▁▂▁▁▂▁▂▁▁▂▁▂▂▂
sd-finetune-qn92w-420816036: wandb:    lr ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
sd-finetune-qn92w-420816036: wandb: 
sd-finetune-qn92w-420816036: wandb: Run summary:
sd-finetune-qn92w-420816036: wandb: epoch 9
sd-finetune-qn92w-420816036: wandb:  loss 0.06736
sd-finetune-qn92w-420816036: wandb:    lr 1e-05
sd-finetune-qn92w-420816036: wandb: 
sd-finetune-qn92w-420816036: wandb: Synced test: https://wandb.ai/haruu/sd-finetune/runs/lfrc5t20
sd-finetune-qn92w-420816036: wandb: Synced 5 W&B file(s), 24 media file(s), 0 artifact file(s) and 0 other file(s)
sd-finetune-qn92w-420816036: wandb: Find logs at: /tmp/wandb/run-20221024_234339-lfrc5t20/logs
```

During finetuning, the time elapsed is displayed, alongside the expected time to complete. Checkpointing and loss reporting is also reported within the logs as well as WandB.

{% hint style="info" %}
**Note**

You can instantly watch a submitted workflow by using the `--watch` option when running the `submit` command:

`argo submit --watch`
{% endhint %}

#### Web UI

You can access your Argo Workflow application via HTTPS to see all the finetuner jobs, and to check their statuses.

<figure><img src="../.gitbook/assets/webui.png" alt=""><figcaption><p>Argo Workflow Web UI</p></figcaption></figure>

## Workflow Options

The following section outlines some useful workflow parameters. This is not intended to be a complete or exhaustive reference on all exposed parameters.

| Parameter                | Description                                                                                                                                                           | Default Value                   |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| `run_name`               | The run name used to name artifacts and report metrics. Should be unique.                                                                                             | N/A                             |
| `pvc`                    | The PVC to use for dataset and model artifacts.                                                                                                                       | `sd-finetune-data`              |
| `region`                 | The region to run the Argo jobs in. Generally, this should be ORD1.                                                                                                   | `ORD1`                          |
| `dataset`                | The path to the dataset inside of the PVC.                                                                                                                            | `dataset`                       |
| `model`                  | The Hugging Face model identifier to pull the Stable Diffusion model from.                                                                                            | `CompVis/stable-diffusion-v1-4` |
| `epochs`                 | The amount of times the finetuner will run through the entire dataset.                                                                                                | `10`                            |
| `batch_size`             | The amount of batches to use in a single optimization step.                                                                                                           | `1`                             |
| `use_ema`                | Whether or not to use EMA during finetuning.                                                                                                                          | `False`                         |
| `ucg`                    | The probability to drop the text condition during finetuning. This helps Classifier-Free Guidance.                                                                    | `0.1`                           |
| `gradient_checkpointing` | Whether or not to perform gradient checkpointing to save VRAM consumption.                                                                                            | `False`                         |
| `use_8bit_adam`          | Whether or not to use 8-bit Adam. This saves VRAM while improving speed but is only supported on a few NVIDIA GPUs.                                                   | `False`                         |
| `adam_beta1`             | Beta 1 hyperparameter for the Adam Optimizer.                                                                                                                         | `0.9`                           |
| `adam_beta2`             | Beta 2 hyperparameter for the Adam Optimizer.                                                                                                                         | `0.999`                         |
| `adam_weight_decay`      | Weight Decay hyperparameter for the Adam Optimizer.                                                                                                                   | `1e-2`                          |
| `adam_epsilon`           | Epsilon hyperparameter for the Adam Optimizer.                                                                                                                        | `1e-08`                         |
| `seed`                   | Seed for random number generator. This is to be used for reproducibility purposes.                                                                                    | `42`                            |
| `save_steps`             | The steps to save the model at.                                                                                                                                       | `500`                           |
| `resolution`             | The image resolution to train the model at.                                                                                                                           | `512`                           |
| `resize`                 | Whether or not to perform image resizing during training. Only set this to True if the images in your dataset are of different resolutions that you want to train at. | `False`                         |
| `center_crop`            | Whether or not to center crop the training images.                                                                                                                    | `False`                         |
| `resize_interp`          | The interpolation method to use for image resizing.                                                                                                                   | `lanczos`                       |
| `shuffle`                | Whether or not to shuffle the dataset.                                                                                                                                | `True`                          |
| `image_log_steps`        | The number of steps at which to log images at for WandB tracking.                                                                                                     | `500`                           |
| `image_log_amount`       | The amount of images to log per each image logging step.                                                                                                              | `4`                             |
| `hf_token`               | The Hugging Face token to use to download private Stable Diffusion models.                                                                                            | N/A                             |
| `wandb_api_key`          | Your WandB API key for tracking the finetune run.                                                                                                                     | N/A                             |
| `project_id`             | The project to report to in WandB.                                                                                                                                    | `diffusers`                     |
| `run_inference`          | Whether or not to run inference at the end of finetuning.                                                                                                             | `False`                         |
| `inference_only`         | Skip training and only run inference. This will only work if the model already exists within your PVC.                                                                | `False`                         |

## Artifacts and Inference

Once the model completes finetuning, the model artifacts should be found under a directory with a name patterned after `{{pvc}}/finetunes/{{run_name}}`.

You can download the model at this point, or you can run the `InferenceService` on the model.

If you followed the directions for Inference Service, and have installed the KNative client, you should be able to get an URL by invoking `kn service list`.

Services can also be listed without the KNative Client by executing `kubectl get ksvc`:

#### Example Output

```
NAME                               URL                                                                                                LATESTCREATED                            LATESTREADY                              READY   REASON
inference-test-predictor-default   http://inference-test-predictor-default.tenant-sta-amercurio-amercurio.knative.chi.coreweave.com   inference-test-predictor-default-00001   inference-test-predictor-default-00001   True    
```

We can run `curl` to do a test query:

```shell-session
curl http://inference-test-predictor-default.tenant-sta-amercurio-amercurio.knative.chi.coreweave.com/v1/models/test:predict \
    -d '{"prompt": "California sunset on the beach, red clouds, Nikon DSLR, professional photography", "parameters": {"seed": 42, "width": 512, "height": 512}}' \
    --output sunset.png
```

#### Example Output

The above command should yield a result and an image similar to the following:

```
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100  292k  100  292k  100   151  31960     16  0:00:09  0:00:09 --:--:-- 72763
```

<figure><img src="../.gitbook/assets/sunset (1).png" alt=""><figcaption><p>California sunset on the beach, red clouds, Nikon DSLR, professional photography</p></figcaption></figure>

The model and dataset have now been run through the finetuning process to do test inferences against the new model.
