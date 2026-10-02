#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <opencv2/opencv.hpp>
#include <vector>
#include <string>
#include "base64.h"

namespace py = pybind11;

std::string encode_frame_in_memory(py::array_t<uint8_t> input) {
    py::buffer_info buf = input.request();
    cv::Mat frame(buf.shape[0], buf.shape[1], CV_8UC3, (unsigned char*)buf.ptr);
    
    std::vector<uchar> buf_jpg;
    // Diske yazmadan RAM üzerinde JPEG formatında sıkıştır
    cv::imencode(".jpg", frame, buf_jpg); 
    
    // RAM'deki veriyi doğrudan Base64 string'e dönüştür
    return base64_encode(buf_jpg.data(), static_cast<unsigned int>(buf_jpg.size()));
}

PYBIND11_MODULE(joi_cpp, m) {
    m.def("encode_frame", &encode_frame_in_memory, "Convert CV2 frame to Base64 in RAM");
}