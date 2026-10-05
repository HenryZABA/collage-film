// Thin CLI for the sam3.cpp public API. Model and inference are supplied by the pinned upstream engine.
#include "sam3.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
int main(int argc,char **argv) {
 if(argc==2 && std::string(argv[1])=="--version"){std::cout<<"collage-sam2-protocol-1\n";return 0;}
 if(argc!=6){fprintf(stderr,"usage: collage-sam2 MODEL INPUT PROMPTS OUTPUT_DIR cpu|metal\n");return 2;}
 std::ifstream in(argv[3]); int count; if(!(in>>count)||count<1||count>64)return 2;
 std::vector<sam3_pvs_params> prompts;
 for(int i=0;i<count;i++) {
  sam3_pvs_params p; int box,np,nn;
  if(!(in>>box>>p.box.x0>>p.box.y0>>p.box.x1>>p.box.y1>>np>>nn)||np<0||nn<0||np+nn>128)return 2;
  p.use_box=box==1;
  for(int j=0;j<np+nn;j++){sam3_point pt; if(!(in>>pt.x>>pt.y))return 2; if(j<np)p.pos_points.push_back(pt);else p.neg_points.push_back(pt);}
  if(!p.use_box&&p.pos_points.empty())return 2;
  p.multimask=false; prompts.push_back(p);
 }
 auto start=std::chrono::steady_clock::now();
 sam3_params params; params.model_path=argv[1]; params.use_gpu=std::string(argv[5])=="metal";
 auto model=sam3_load_model(params); if(!model)return 3;
 auto state=sam3_create_state(*model,params);if(!state)return 3;
 auto image=sam3_load_image(argv[2]);if(image.width<=0||image.height<=0)return 4;
 if(!sam3_encode_image(*state,*model,image))return 5;
 std::cout<<"{\"width\":"<<image.width<<",\"height\":"<<image.height<<",\"objects\":[";
 for(int i=0;i<count;i++) {
  auto &p=prompts[i];p.box.x0*=image.width;p.box.x1*=image.width;p.box.y0*=image.height;p.box.y1*=image.height;
  for(auto&pt:p.pos_points){pt.x=std::min(float(image.width-1),pt.x*image.width);pt.y=std::min(float(image.height-1),pt.y*image.height);}
  for(auto&pt:p.neg_points){pt.x=std::min(float(image.width-1),pt.x*image.width);pt.y=std::min(float(image.height-1),pt.y*image.height);}
  auto result=sam3_segment_pvs(*state,*model,p); if(result.detections.empty())return 6;
  const auto &det=result.detections[0];std::string filename="mask-"+std::to_string(i)+".png";
  if(!sam3_save_mask(det.mask,std::string(argv[4])+"/"+filename))return 7;
  if(i)std::cout<<",";
  std::cout<<"{\"index\":"<<i<<",\"mask\":\""<<filename<<"\",\"iou_score\":"<<det.iou_score<<",\"object_score\":"<<det.mask.obj_score<<"}";
 }
 double sec=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
 std::cout<<"],\"elapsed_seconds\":"<<sec<<"}"<<std::endl;return 0;
}
